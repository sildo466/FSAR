// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { ClientMsg } from '../../lib/ws-client'
import { initI18n } from '../../lib/i18nSetup'
import { useWS } from '../../stores/ws'
import { StepBirthday } from './StepBirthday'

class Client {
  sent: ClientMsg[] = []
  send(message: ClientMsg) { this.sent.push(message) }
}

beforeAll(async () => {
  await initI18n('en')
})

afterEach(cleanup)

it('saves a zero-padded birthday and advances', () => {
  const client = new Client()
  const onNext = vi.fn()
  useWS.setState({ client: client as never, config: {} })
  render(<StepBirthday onNext={onNext} onSkip={() => {}} />)
  fireEvent.change(screen.getByTestId('birthday-month-input'), { target: { value: '3' } })
  fireEvent.change(screen.getByTestId('birthday-day-input'), { target: { value: '4' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save & Next' }))
  expect(client.sent).toContainEqual({
    type: 'settings.patch',
    patch: { 'user.birthday': '03-04' },
  })
  expect(client.sent).toContainEqual({
    type: 'onboarding.complete_step',
    step: 'birthday',
    data: { birthday: '03-04' },
  })
  expect(onNext).toHaveBeenCalled()
})

it('refuses an impossible date', () => {
  const client = new Client()
  const onNext = vi.fn()
  useWS.setState({ client: client as never, config: {} })
  render(<StepBirthday onNext={onNext} onSkip={() => {}} />)
  fireEvent.change(screen.getByTestId('birthday-month-input'), { target: { value: '2' } })
  fireEvent.change(screen.getByTestId('birthday-day-input'), { target: { value: '30' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save & Next' }))
  expect(client.sent).toEqual([])
  expect(onNext).not.toHaveBeenCalled()
})

it('skips without writing a birthday', () => {
  const client = new Client()
  useWS.setState({ client: client as never, config: {} })
  render(<StepBirthday onNext={() => {}} onSkip={() => {}} />)
  fireEvent.click(screen.getByRole('button', { name: 'Skip setup' }))
  expect(client.sent).toEqual([{ type: 'onboarding.skip_step', step: 'birthday' }])
})

it('prefills from an already stored birthday', () => {
  useWS.setState({ client: new Client() as never, config: { user: { birthday: '03-14' } } })
  render(<StepBirthday onNext={() => {}} onSkip={() => {}} />)
  expect(screen.getByTestId('birthday-month-input')).toHaveValue('3')
  expect(screen.getByTestId('birthday-day-input')).toHaveValue('14')
})
