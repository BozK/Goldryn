import { describe, expect, it } from 'vitest'
import type { TagSummary } from './GoldrynModels'
import { normalizeTag, suggestTags } from './tags'

const tags = (...names: string[]): TagSummary[] => names.map((name) => ({ name, item_count: 1 }))

describe('normalizeTag', () => {
  it('lowercases and collapses whitespace', () => {
    expect(normalizeTag('  Water   Heater ')).toBe('water heater')
  })

  it('turns whitespace-only text into an empty string', () => {
    expect(normalizeTag(' \t ')).toBe('')
  })
})

describe('suggestTags', () => {
  const all = tags('hvac', 'kitchen', 'outside', 'basement', 'attic')

  it('lists the most-used tags when nothing is typed', () => {
    expect(suggestTags(all, '', [])).toEqual(['hvac', 'kitchen', 'outside', 'basement', 'attic'])
  })

  it('puts prefix matches before substring matches, keeping server order', () => {
    expect(suggestTags(tags('basement', 'attic', 'atrium'), 'At', [])).toEqual(['attic', 'atrium'])
    expect(suggestTags(tags('kitchen', 'tank', 'attic', 'trim'), 't', [])).toEqual(['tank', 'trim', 'kitchen', 'attic'])
  })

  it('leaves out tags already on the item', () => {
    expect(suggestTags(all, '', ['hvac', 'attic'])).toEqual(['kitchen', 'outside', 'basement'])
  })

  it('caps the list at 8', () => {
    const many = tags(...Array.from({ length: 12 }, (_, i) => `tag ${i}`))
    expect(suggestTags(many, 'tag', [])).toHaveLength(8)
  })

  it('returns nothing when nothing matches', () => {
    expect(suggestTags(all, 'garage', [])).toEqual([])
  })
})
