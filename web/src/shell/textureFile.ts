// "Abrir .dds": abre a textura no programa padrão do sistema (Paint.NET etc.), como a clássica.
import { call } from '../bridge'
import { t } from '../i18n'
import { message } from '../ui/dialogs'

export async function openTextureFile(xmlPath: string, texture: string): Promise<void> {
  const result = await call<'ok' | 'missing' | 'failed'>('open_texture_file', xmlPath, texture)
  if (result === 'missing')
    await message('warning', t('Abrir .dds'), t('O arquivo de textura não foi encontrado: {path}', { path: texture }))
  else if (result === 'failed')
    await message(
      'warning',
      t('Abrir .dds'),
      t('Não foi possível abrir {name}. Verifique o aplicativo padrão para arquivos .dds no sistema.', { name: texture }),
    )
}
