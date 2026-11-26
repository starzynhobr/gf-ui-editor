import { describe, expect, it } from 'vitest'
import { decodeTga } from '../canvas/dds/tga'
import { cropBetween, moveCrop, resizeCrop } from './geometry'

describe('atlas gestures', () => {
  it('snaps within the image and handles reversed drags', () => {
    expect(cropBetween([23.7, 18.9], [-5, 6.2], [24, 18])).toEqual([0, 6, 24, 12])
    expect(cropBetween([24, 18], [24, 18], [24, 18])).toEqual([23, 17, 1, 1])
    expect(moveCrop([3, 4, 8, 7], [99, -99], [24, 18])).toEqual([16, 0, 8, 7])
    expect(resizeCrop([3, 4, 8, 7], 'w', [14, 15], [24, 18])).toEqual([11, 4, 3, 7])
  })
})

describe('TGA previews', () => {
  it('decodes bottom-right origin and RLE packets with alpha', () => {
    const header = [0, 0, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 2, 0, 32, 24]
    const bytes = Uint8Array.from([...header,
      129, 1, 2, 3, 4,
      1, 5, 6, 7, 8, 9, 10, 11, 12,
    ])
    expect([...decodeTga(bytes.buffer).rgba]).toEqual([
      11, 10, 9, 12, 7, 6, 5, 8,
      3, 2, 1, 4, 3, 2, 1, 4,
    ])
  })
})
