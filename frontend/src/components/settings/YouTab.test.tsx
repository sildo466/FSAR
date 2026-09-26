// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { ClientMsg } from '../../lib/ws-client'
import { initI18n } from '../../lib/i18nSetup'
import { useWS } from '../../stores/ws'
import { YouTab } from './YouTab'

class Client {
  sent: ClientMsg[] = []
  send(message: ClientMsg) { this.sent.push(message) }
}

beforeAll(async () => {
  await initI18n('en')
})

afterEach(cleanup)

it('shows the stored birthday and saves a new one', () => {
  const client = new Client()
  useWS.setState({ client: client as never, config: { user: { birthday: '03-14' } } })
  render(<YouTab />)
  expect(screen.getByTestId('you-birthday-month')).toHaveValue('3')
  fireEvent.change(screen.getByTestId('you-birthday-day'), { target: { value: '15' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(client.sent).toContainEqual({
    type: 'settings.patch',
    patch: { 'user.birthday': '03-15' },
  })
})

it('rejects an impossible date', () => {
  const client = new Client()
  useWS.setState({ client: client as never, config: {} })
  render(<YouTab />)
  fireEvent.change(screen.getByTestId('you-birthday-month'), { target: { value: '2' } })
  fireEvent.change(screen.getByTestId('you-birthday-day'), { target: { value: '30' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(client.sent).toEqual([])
  expect(screen.getByRole('alert')).toBeInTheDocument()
})

it('clears a stored birthday', () => {
  const client = new Client()
  useWS.setState({ client: client as never, config: { user: { birthday: '03-14' } } })
  render(<YouTab />)
  fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
  expect(client.sent).toContainEqual({
    type: 'settings.patch',
    patch: { 'user.birthday': null },
  })
})
