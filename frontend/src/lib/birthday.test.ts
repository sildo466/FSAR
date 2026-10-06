// SPDX-License-Identifier: MIT
import { describe, expect, it } from 'vitest'
import { isValidBirthday, joinBirthday, splitBirthday } from './birthday'

describe('splitBirthday', () => {
  it('splits a stored MM-DD without keeping the zero padding', () => {
    expect(splitBirthday('03-14')).toEqual({ month: '3', day: '14' })
    expect(splitBirthday('12-31')).toEqual({ month: '12', day: '31' })
  })

  it('returns empties for anything unusable', () => {
    expect(splitBirthday(null)).toEqual({ month: '', day: '' })
    expect(splitBirthday(undefined)).toEqual({ month: '', day: '' })
    expect(splitBirthday('')).toEqual({ month: '', day: '' })
    expect(splitBirthday('garbage')).toEqual({ month: '', day: '' })
    expect(splitBirthday('2026-03-14')).toEqual({ month: '', day: '' })
    expect(splitBirthday(314)).toEqual({ month: '', day: '' })
  })
})

describe('isValidBirthday', () => {
  it('accepts real calendar dates', () => {
    expect(isValidBirthday(1, 1)).toBe(true)
    expect(isValidBirthday(12, 31)).toBe(true)
    expect(isValidBirthday(2, 29)).toBe(true)
    expect(isValidBirthday(6, 30)).toBe(true)
  })

  it('rejects impossible dates', () => {
    expect(isValidBirthday(0, 10)).toBe(false)
    expect(isValidBirthday(13, 1)).toBe(false)
    expect(isValidBirthday(2, 30)).toBe(false)
    expect(isValidBirthday(4, 31)).toBe(false)
    expect(isValidBirthday(1, 0)).toBe(false)
    expect(isValidBirthday(1, 32)).toBe(false)
  })
})

describe('joinBirthday', () => {
  it('zero-pads a valid pair', () => {
    expect(joinBirthday('3', '4')).toBe('03-04')
    expect(joinBirthday('12', '31')).toBe('12-31')
    expect(joinBirthday('2', '29')).toBe('02-29')
  })

  it('returns null when either half is unusable', () => {
    expect(joinBirthday('', '4')).toBe(null)
    expect(joinBirthday('3', '')).toBe(null)
    expect(joinBirthday('abc', '4')).toBe(null)
    expect(joinBirthday('2', '30')).toBe(null)
    expect(joinBirthday('3.5', '4')).toBe(null)
  })
})
