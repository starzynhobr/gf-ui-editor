/** DDS top mip level, in the same straight RGBA layout as Pillow. */
export function decodeDds(buffer: ArrayBuffer) {
  const header = new DataView(buffer)
  if (header.byteLength < 128 || header.getUint32(0, true) !== 0x20534444
      || header.getUint32(4, true) !== 124 || header.getUint32(76, true) !== 32) {
    throw new Error('Invalid DDS header')
  }
  const width = header.getUint32(16, true)
  const height = header.getUint32(12, true)
  if (!width || !height || width * height > 4096 * 4096 * 4) throw new Error('Invalid DDS dimensions')

  const flags = header.getUint32(80, true)
  const bytes = new Uint8Array(buffer, 128)
  const rgba = new Uint8ClampedArray(width * height * 4)
  if (flags & 4) {
    const format = String.fromCharCode(...new Uint8Array(buffer, 84, 4))
    decodeBlocks(bytes, rgba, width, height, format)
  } else {
    const bits = header.getUint32(88, true)
    const masks = [92, 96, 100, 104].map((offset) => header.getUint32(offset, true))
    decodePixels(bytes, rgba, bits, flags, masks)
  }
  return { rgba, width, height }
}

function decodePixels(
  bytes: Uint8Array, rgba: Uint8ClampedArray, bits: number, flags: number, masks: number[],
) {
  const stride = bits / 8
  if (![1, 2, 3, 4].includes(stride) || bytes.length < rgba.length / 4 * stride) {
    throw new Error('Invalid DDS pixel data')
  }
  // Fast path for the 32 bpp layouts used by most atlases.
  if (bits === 32 && (masks[0] === 0xff0000 || masks[0] === 0xff) && masks[1] === 0xff00
      && (masks[0] | masks[2]) === 0xff00ff && (!masks[3] || masks[3] === 0xff000000)) {
    const red = masks[0] === 0xff ? 0 : 2
    for (let i = 0; i < rgba.length; i += 4) {
      rgba[i] = bytes[i + red]
      rgba[i + 1] = bytes[i + 1]
      rgba[i + 2] = bytes[i + 2 - red]
      rgba[i + 3] = masks[3] ? bytes[i + 3] : 255
    }
    return
  }
  if (bits === 8 && flags & 0x20) {
    const paletteSize = 256 * 4
    if (bytes.length < paletteSize + rgba.length / 4) throw new Error('Truncated DDS palette')
    for (let i = 0; i < rgba.length; i += 4) {
      const entry = bytes[paletteSize + i / 4] * 4
      rgba.set(bytes.subarray(entry, entry + 4), i)
    }
    return
  }
  if (!(flags & 0x40)) throw new Error('Unsupported DDS pixel format')
  const channels = masks.map((mask, channel) => {
    if (!mask) return () => channel === 3 ? 255 : 0
    const shift = 31 - Math.clz32(mask & -mask)
    const max = mask >>> shift
    return (pixel: number) => Math.floor(((pixel & mask) >>> shift) * 255 / max)
  })
  for (let i = 0, source = 0; i < rgba.length; i += 4, source += stride) {
    let pixel = 0
    for (let byte = 0; byte < stride; byte++) pixel |= bytes[source + byte] << (8 * byte)
    for (let channel = 0; channel < 4; channel++) rgba[i + channel] = channels[channel](pixel)
  }
}

function rgb565(pixel: number): number[] {
  const red = pixel >> 11
  const green = (pixel >> 5) & 63
  const blue = pixel & 31
  return [(red << 3) | (red >> 2), (green << 2) | (green >> 4), (blue << 3) | (blue >> 2), 255]
}

function decodeBlocks(bytes: Uint8Array, rgba: Uint8ClampedArray, width: number, height: number, format: string) {
  if (!['DXT1', 'DXT3', 'DXT5'].includes(format)) throw new Error(`Unsupported DDS format: ${format}`)
  const stride = format === 'DXT1' ? 8 : 16
  if (bytes.length < Math.ceil(width / 4) * Math.ceil(height / 4) * stride) {
    throw new Error('Truncated DDS blocks')
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  let block = 0
  for (let top = 0; top < height; top += 4) {
    for (let left = 0; left < width; left += 4, block += stride) {
      const colorOffset = block + stride - 8
      const c0 = view.getUint16(colorOffset, true)
      const c1 = view.getUint16(colorOffset + 2, true)
      const colorCodes = view.getUint32(colorOffset + 4, true)
      const a = rgb565(c0)
      const b = rgb565(c1)
      const transparent = format === 'DXT1' && c0 <= c1
      const colors = [a, b]
      colors.push(a.map((v, i) => Math.floor(transparent ? (v + b[i]) / 2 : (2 * v + b[i]) / 3)))
      colors.push(transparent ? [0, 0, 0, 0] : a.map((v, i) => Math.floor((v + 2 * b[i]) / 3)))

      const alphaTable = [bytes[block], bytes[block + 1]]
      if (format === 'DXT5') {
        const [a0, a1] = alphaTable
        const steps = a0 > a1 ? 7 : 5
        for (let i = 1; i < steps; i++) alphaTable.push(Math.floor(((steps - i) * a0 + i * a1) / steps))
        if (steps === 5) alphaTable.push(0, 255)
      }
      for (let y = 0; y < 4 && top + y < height; y++) {
        for (let x = 0; x < 4 && left + x < width; x++) {
          const i = y * 4 + x
          const pixel = ((top + y) * width + left + x) * 4
          const color = colors[(colorCodes >>> (2 * i)) & 3]
          rgba.set(color, pixel)
          if (format === 'DXT3') {
            rgba[pixel + 3] = ((bytes[block + (i >> 1)] >> (4 * (i & 1))) & 15) * 17
          } else if (format === 'DXT5') {
            const bit = i * 3
            const index = block + 2 + (bit >> 3)
            const code = (bytes[index] | bytes[index + 1] << 8) >> (bit & 7)
            rgba[pixel + 3] = alphaTable[code & 7]
          }
        }
      }
    }
  }
}
