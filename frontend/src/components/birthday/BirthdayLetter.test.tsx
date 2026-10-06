// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { initI18n } from '../../lib/i18nSetup'
import { useWS } from '../../stores/ws'
import { BirthdayLetter } from './BirthdayLetter'

beforeAll(async () => {
  await initI18n('en')
})

afterEach(cleanup)

it('renders nothing when there is no letter', () => {
  useWS.setState({ birthdayLetter: null })
  const { container } = render(<BirthdayLetter />)
  expect(container).toBeEmptyDOMElement()
})

it('renders each paragraph and dismisses on click', () => {
  useWS.setState({ birthdayLetter: 'Happy birthday!\n\nToday is your day.\n\n— FSAR' })
  render(<BirthdayLetter />)
  expect(screen.getByTestId('birthday-paragraphs').children).toHaveLength(3)
  expect(screen.getByText('Today is your day.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
  expect(screen.queryByTestId('birthday-letter')).not.toBeInTheDocument()
})

it('covers the screen and is never a translucent glass panel', () => {
  useWS.setState({ birthdayLetter: 'hi' })
  render(<BirthdayLetter />)
  const shell = screen.getByTestId('birthday-letter')
  expect(shell.className).toMatch(/fixed inset-0/)
  expect(shell.className).not.toMatch(/glass/)
  expect(shell.getAttribute('style')).not.toMatch(/rgba\(255,255,255,\.0/)
  expect(shell.dataset.opaque).toBe('true')
})
