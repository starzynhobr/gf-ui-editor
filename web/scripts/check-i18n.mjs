// Confere que todo t('...') do front tem tradução nos 4 idiomas.
//
//   node scripts/check-i18n.mjs        (npm run i18n:check; roda também no build)
//
// Procura chamadas t('texto') / t("texto") com texto literal em src/ e exige o texto nos
// catálogos do Qt (src/i18n/catalogs) ou em src/i18n/web-strings.json, em en_US, es_ES e fr_FR.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const src = join(here, '..', 'src')
const LANGUAGES = ['en_US', 'es_ES', 'fr_FR']

const catalogs = Object.fromEntries(
  LANGUAGES.map((language) => [language, JSON.parse(readFileSync(join(src, 'i18n', 'catalogs', `${language}.json`), 'utf8'))]),
)
const web = JSON.parse(readFileSync(join(src, 'i18n', 'web-strings.json'), 'utf8'))

function* files(folder) {
  for (const name of readdirSync(folder)) {
    const path = join(folder, name)
    if (statSync(path).isDirectory()) yield* files(path)
    else if (/\.tsx?$/.test(name)) yield path
  }
}

const unescape = (text) => text.replace(/\\(['"\\])/g, '$1').replace(/\\n/g, '\n')
const missing = new Map()
let total = 0
for (const path of files(src)) {
  const code = readFileSync(path, 'utf8')
  for (const match of code.matchAll(/\bt\(\s*(['"])((?:\\.|(?!\1).)*)\1/g)) {
    const key = unescape(match[2])
    total += 1
    for (const language of LANGUAGES) {
      if (!catalogs[language][key] && !web[key]?.[language]) {
        if (!missing.has(key)) missing.set(key, new Set())
        missing.get(key).add(language)
      }
    }
  }
}
if (missing.size) {
  for (const [key, languages] of missing) console.error(`sem tradução (${[...languages].join(', ')}): ${JSON.stringify(key)}`)
  process.exit(1)
}
console.log(`i18n ok: ${total} chamadas de t() traduzidas nos 4 idiomas`)
