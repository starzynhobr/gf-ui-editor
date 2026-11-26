/** TGA image data in top-left, straight RGBA order. */
export function decodeTga(buffer: ArrayBuffer) {
  const header = new DataView(buffer)
  if (header.byteLength < 18) throw new Error('Invalid TGA header')
  const mapType = header.getUint8(1)
  const type = header.getUint8(2)
  const rle = type >= 9 && type <= 11
  const imageType = rle ? type - 8 : type
  const depth = header.getUint8(16)
  const descriptor = header.getUint8(17)
  const width = header.getUint16(12, true)
  const height = header.getUint16(14, true)
  const depths = [[8, 16], [15, 16, 24, 32], [8, 16]]
  if (!width || !height || width * height > 4096 * 4096 * 4 || descriptor & 0xc0 ||
      !depths[imageType - 1]?.includes(depth) || mapType !== (imageType === 1 ? 1 : 0)) {
    throw new Error('Unsupported TGA image')
  }

  let offset = 18 + header.getUint8(0)
  const palette = new Map<number, number[]>()
  function color(bits: number, grayscale: boolean): number[] {
    const first = header.getUint8(offset++)
    if (grayscale) {
      return [first, first, first, bits === 16 ? header.getUint8(offset++) : 255]
    }
    const second = header.getUint8(offset++)
    if (bits <= 16) {
      const value = first | (second << 8)
      const expand = (n: number) => Math.floor((n & 31) * 255 / 31)
      return [expand(value >> 10), expand(value >> 5), expand(value), 255]
    }
    const red = header.getUint8(offset++)
    return [red, second, first, bits === 32 ? header.getUint8(offset++) : 255]
  }

  if (mapType) {
    const start = header.getUint16(3, true)
    const end = start + header.getUint16(5, true)
    const bits = header.getUint8(7)
    if (!depths[1].includes(bits)) throw new Error('Unsupported TGA palette')
    for (let index = start; index < end; index++) palette.set(index, color(bits, false))
  }

  function pixel() {
    if (!mapType) return color(depth, imageType === 3)
    const index = depth === 8 ? header.getUint8(offset) : header.getUint16(offset, true)
    offset += depth / 8
    const entry = palette.get(index)
    if (!entry) throw new Error('Invalid TGA palette index')
    return entry
  }

  const rgba = new Uint8ClampedArray(width * height * 4)
  const top = Boolean(descriptor & 0x20)
  const right = Boolean(descriptor & 0x10)
  let position = 0
  while (position < width * height) {
    const packet = rle ? header.getUint8(offset++) : 0
    const count = (packet & 127) + 1
    if (position + count > width * height) throw new Error('Invalid TGA packet')
    const repeated = packet & 128 ? pixel() : null
    for (let index = 0; index < count; index++, position++) {
      const column = position % width
      const row = Math.floor(position / width)
      const x = right ? width - 1 - column : column
      const y = top ? row : height - 1 - row
      rgba.set(repeated ?? pixel(), (y * width + x) * 4)
    }
  }
  return { width, height, rgba }
}
