// SPDX-License-Identifier: MIT
const STORED = /^(\d{2})-(\d{2})$/
// A leap year, so 02-29 passes the day-of-month bound.
const LEAP_YEAR = 2024

export function splitBirthday(raw: unknown): { month: string; day: string } {
  if (typeof raw !== 'string') return { month: '', day: '' }
  const match = STORED.exec(raw.trim())
  if (!match) return { month: '', day: '' }
  return { month: String(Number(match[1])), day: String(Number(match[2])) }
}

export function isValidBirthday(month: number, day: number): boolean {
  if (!Number.isInteger(month) || !Number.isInteger(day)) return false
  if (month < 1 || month > 12) return false
  if (day < 1) return false
  return day <= new Date(LEAP_YEAR, month, 0).getDate()
}

export function joinBirthday(month: string, day: string): string | null {
  if (!month.trim() || !day.trim()) return null
  const m = Number(month)
  const d = Number(day)
  if (!isValidBirthday(m, d)) return null
  return `${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
}
