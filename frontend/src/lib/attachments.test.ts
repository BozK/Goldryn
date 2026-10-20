import { describe, expect, it } from 'vitest'
import { formatSize, opensInTab, typeLabel } from './attachments'

describe('formatSize', () => {
  it('keeps bytes under 1 KB as bytes', () => {
    expect(formatSize(0)).toBe('0 B')
    expect(formatSize(1023)).toBe('1023 B')
  })

  it('shows one decimal under 10 and whole numbers above', () => {
    expect(formatSize(1024)).toBe('1.0 KB')
    expect(formatSize(14_000)).toBe('14 KB')
    expect(formatSize(2_500_000)).toBe('2.4 MB')
    expect(formatSize(50 * 1024 * 1024)).toBe('50 MB')
  })
})

describe('typeLabel', () => {
  it('uppercases the extension', () => {
    expect(typeLabel('manual.pdf')).toBe('PDF')
    expect(typeLabel('warranty.Docx')).toBe('DOCX')
    expect(typeLabel('archive.tar.gz')).toBe('GZ')
  })

  it('falls back to FILE without a short extension', () => {
    expect(typeLabel('README')).toBe('FILE')
    expect(typeLabel('.env')).toBe('FILE')
    expect(typeLabel('notes.')).toBe('FILE')
    expect(typeLabel('scan.verylongext')).toBe('FILE')
  })
})

describe('opensInTab', () => {
  it('opens images, PDFs and text, and downloads anything else', () => {
    expect(opensInTab('image')).toBe(true)
    expect(opensInTab('pdf')).toBe(true)
    expect(opensInTab('text')).toBe(true)
    expect(opensInTab('file')).toBe(false)
  })
})
