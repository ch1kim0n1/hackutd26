import { readFileSync, readdirSync, existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../', import.meta.url))
const pkg = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'))
const lock = JSON.parse(readFileSync(join(root, 'package-lock.json'), 'utf8'))
const noticePattern = /^(licen[cs]e|copying|notice|copyright|ofl)([._-].*)?$/i
const inventory = []
const notices = ['Phantom Command third-party notices\nGenerated from the installed npm lockfile. Includes development dependencies.\nRedistribute this file with built assets. shadcn source is MIT licensed; see the notice below.\n']

for (const relative of Object.keys(lock.packages).filter(key => key.includes('node_modules/')).sort()) {
  const directory = resolve(root, relative)
  const path = join(directory, 'package.json')
  if (!existsSync(path)) continue // platform-specific optional dependencies
  const item = JSON.parse(readFileSync(path, 'utf8'))
  const verifiedLegacy = { khroma: 'MIT', 'webgl-constants': 'MIT' } // verified from their shipped license files
  const license = typeof item.license === 'string' ? item.license : item.license?.type ?? item.licenses?.map(value => value.type).join(' OR ') ?? verifiedLegacy[item.name] ?? 'See upstream notices'
  const repo = typeof item.repository === 'string' ? item.repository : item.repository?.url ?? item.homepage ?? ''
  let url = repo.replace(/^git\+/, '').replace(/^git:\/\//, 'https://').replace(/^ssh:\/\/git@github.com\//, 'https://github.com/').replace(/^git@github.com:/, 'https://github.com/').replace(/^github:/, 'https://github.com/').replace(/\.git$/, '')
  if (/^[\w.-]+\/[\w.-]+$/.test(url)) url = `https://github.com/${url}`
  if (item.name === 'react-grid-layout') url = 'https://github.com/react-grid-layout/react-grid-layout'
  if (item.name === 'webgl-constants') url = 'https://github.com/TimvanScherpenzeel/webgl-constants'
  inventory.push({ name: item.name, version: item.version, license, repository: url, path: relative })
  const files = readdirSync(directory, { withFileTypes: true }).filter(entry => entry.isFile() && noticePattern.test(entry.name)).map(entry => entry.name)
  const legalDir = join(directory, 'LICENSES')
  if (existsSync(legalDir)) for (const entry of readdirSync(legalDir, { withFileTypes: true })) if (entry.isFile()) files.push(`LICENSES/${entry.name}`)
  notices.push(`\n${'='.repeat(72)}\n${item.name}@${item.version}\nLicense: ${license}\nRepository: ${url}\n`)
  if (!files.length) notices.push(`No standalone license file is shipped by this npm package. Refer to its declared license and official repository.\n`)
  for (const name of files.sort()) notices.push(`\n--- ${name} ---\n${readFileSync(join(directory, name), 'utf8')}\n`)
  if (item.name === 'format') {
    const readme = readFileSync(join(directory, 'Readme.md'), 'utf8')
    notices.push(readme.slice(readme.lastIndexOf('\nLicense\n')))
    const source = readFileSync(join(directory, 'format.js'), 'utf8')
    const header = source.match(/\/\*[\s\S]*?\*\//)?.[0]
    if (header) notices.push(header)
  }
}

// All copied components retain shadcn's upstream copyright notice, from the installed CLI package.
const shadcnNotice = readFileSync(join(root, 'node_modules/shadcn/LICENSE.md'), 'utf8')
notices.unshift(`shadcn/ui copied component source (MIT):\n${shadcnNotice}\n`)
mkdirSync(join(root, 'public'), { recursive: true })
writeFileSync(join(root, 'public/THIRD_PARTY_NOTICES.txt'), notices.join('\n'))
writeFileSync(join(root, 'DEPENDENCY_INVENTORY.json'), JSON.stringify(inventory, null, 2) + '\n')
const rows = []
for (const [group, dependencies] of Object.entries({ Runtime: pkg.dependencies, Development: pkg.devDependencies })) {
  for (const name of Object.keys(dependencies).sort()) {
    const item = inventory.find(entry => entry.path === `node_modules/${name}`)
    if (!item) throw new Error(`Missing installed dependency: ${name}`)
    rows.push(`| ${name} | ${item.version} | ${item.license} | ${group} | [repository](${item.repository}) |`)
  }
}
writeFileSync(join(root, 'THIRD_PARTY_LICENSES.md'), `# Third-party licenses\n\nExact direct dependency versions from the installed lockfile. Community/open-source editions only. Generated with \`npm run licenses\`.\n\n| Package | Version | License | Use | Official source |\n|---|---|---|---|---|\n${rows.join('\n')}\n\nshadcn/ui component source was acquired with the official shadcn CLI (Radix Nova registry; Form uses the official New York registry). Its MIT copyright notice is retained in [public/THIRD_PARTY_NOTICES.txt](public/THIRD_PARTY_NOTICES.txt), together with license/NOTICE files shipped by installed direct and transitive packages. ECharts and RxJS Apache notices and the bundled Geist font license are included. The full installed inventory is [DEPENDENCY_INVENTORY.json](DEPENDENCY_INVENTORY.json).\n\nThe notices file is copied unchanged into the production build. AG Grid Enterprise and paid CopilotKit services are not installed. No third-party models, 3D assets, textures, or remote fonts are used.\n`)
console.log(`Recorded ${inventory.length} installed packages and ${rows.length} direct dependencies; preserved shipped notices.`)
