// Cabeçalho de .dds/.tga para o cartão de prévia da lista de Texturas: dimensões e formato
// (DXT1, ARGB 32…). Só lê os primeiros bytes; a imagem vem do decodificador do canvas.

export interface TextureHeader {
  width: number
  height: number
  format: string
}

/** Bytes que bastam para descrever o arquivo (cabeçalho DDS inteiro; o da TGA é menor). */
export const HEADER_BYTES = 128

export function describeTexture(bytes: Uint8Array, name: string): TextureHeader | null {
  return name.toLowerCase().endsWith('.tga') ? describeTga(bytes) : describeDds(bytes)
}

function describeDds(bytes: Uint8Array): TextureHeader | null {
  if (bytes.byteLength < HEADER_BYTES) return null
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  if (view.getUint32(0, true) !== 0x20534444 || view.getUint32(4, true) !== 124) return null
  const height = view.getUint32(12, true)
  const width = view.getUint32(16, true)
  if (!width || !height) return null
  const flags = view.getUint32(80, true)
  const bits = view.getUint32(88, true)
  const [red, , , alpha] = [92, 96, 100, 104].map((offset) => view.getUint32(offset, true))
  const hasAlpha = Boolean(flags & 0x1) && alpha !== 0
  let format: string
  if (flags & 0x4) {
    const code = bytes.subarray(84, 88)
    const text = String.fromCharCode(...code)
    format = /^[\x20-\x7e]{4}$/.test(text) ? text.trim() : `D3DFMT ${view.getUint32(84, true)}`
  } else if (flags & 0x20) {
    format = 'P8'
  } else if (flags & 0x20000) {
    format = hasAlpha ? `A${bits / 2}L${bits / 2}` : `L${bits}`
  } else if (flags & 0x40) {
    if (bits === 32) format = hasAlpha ? (red === 0xff ? 'ABGR 32' : 'ARGB 32') : 'XRGB 32'
    else if (bits === 24) format = 'RGB 24'
    else if (bits === 16 && red === 0xf800) format = 'RGB 565'
    else if (bits === 16 && red === 0x7c00) format = hasAlpha ? 'ARGB 1555' : 'XRGB 1555'
    else if (bits === 16 && red === 0x0f00) format = hasAlpha ? 'ARGB 4444' : 'XRGB 4444'
    else format = `${hasAlpha ? 'ARGB' : 'RGB'} ${bits}`
  } else if (flags & 0x2) {
    format = `A${bits}`
  } else {
    format = `${bits} bits`
  }
  return { width, height, format }
}

function describeTga(bytes: Uint8Array): TextureHeader | null {
  if (bytes.byteLength < 18) return null
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const type = bytes[2]
  const width = view.getUint16(12, true)
  const height = view.getUint16(14, true)
  const bits = bytes[16]
  if (!width || !height || ![1, 2, 3, 9, 10, 11].includes(type)) return null
  const kind = type === 1 || type === 9 ? 'P' : type === 3 || type === 11 ? 'L' : bits === 32 ? 'ARGB' : 'RGB'
  return { width, height, format: `TGA ${kind} ${bits}${type >= 9 ? ' RLE' : ''}` }
}
