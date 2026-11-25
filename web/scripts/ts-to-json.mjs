// Converte os catálogos do Qt (src/gf_ui_editor/translations/*.ts) em JSON para o front.
//
//   node scripts/ts-to-json.mjs        (npm run i18n)
//
// pt_BR é o texto-fonte: a chave é o <source> e o valor é a <translation>. Os contextos do
// Qt (classes) são achatados; se o mesmo texto tiver traduções diferentes, vale a primeira.
// Textos só da interface nova ficam em src/i18n/web-strings.json (pt_BR -> outros idiomas).
import { readdirSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const translations = join(here, '..', '..', 'src', 'gf_ui_editor', 'translations')
const output = join(here, '..', 'src', 'i18n', 'catalogs')

const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" }

export function decode(raw) {
  const text = raw.replace(/\r\n/g, '\n') // os .ts ficam com CRLF no Windows; o Python usa \n
  return text.replace(/&(#x[0-9a-f]+|#\d+|\w+);/gi, (match, entity) => {
    if (entity[0] === '#') {
      const code = entity[1].toLowerCase() === 'x' ? parseInt(entity.slice(2), 16) : parseInt(entity.slice(1), 10)
      return String.fromCodePoint(code)
    }
    return ENTITIES[entity] ?? match
  })
}

export function parseTs(xml) {
  const catalog = {}
  for (const [, body] of xml.matchAll(/<message\b[^>]*>([\s\S]*?)<\/message>/g)) {
    const source = body.match(/<source>([\s\S]*?)<\/source>/)
    const translation = body.match(/<translation\b([^>]*)>([\s\S]*?)<\/translation>/)
    if (!source || !translation) continue
    if (/type="(unfinished|obsolete|vanished)"/.test(translation[1])) continue
    const key = decode(source[1])
    const value = decode(translation[2])
    if (value && !(key in catalog)) catalog[key] = value
  }
  return catalog
}

function main() {
  mkdirSync(output, { recursive: true })
  for (const name of readdirSync(translations).sort()) {
    const match = name.match(/^gf_ui_editor_(\w+)\.ts$/)
    if (!match) continue
    const catalog = parseTs(readFileSync(join(translations, name), 'utf8'))
    const sorted = Object.fromEntries(Object.entries(catalog).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)))
    writeFileSync(join(output, `${match[1]}.json`), JSON.stringify(sorted, null, 1) + '\n')
    console.log(`${match[1]}: ${Object.keys(sorted).length} textos`)
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main()
