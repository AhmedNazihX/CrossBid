/**
 * The company's own provider key (S5.4, S4.6.4).
 *
 * What these pin is a billing boundary. Before it, every model call went out on one shared
 * application key: one account paid for everyone, and a cap reached on it stopped every
 * account at once. So the card has to make two things unmistakable — that no key means no
 * work, and which key is in force — without ever showing the key itself.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ProviderKeyCard } from './provider-key-card'

const { loadMock, saveMock, deleteMock } = vi.hoisted(() => ({
  loadMock: vi.fn(),
  saveMock: vi.fn(),
  deleteMock: vi.fn(),
}))

vi.mock('@/lib/provider-keys', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/provider-keys')>('@/lib/provider-keys')
  return {
    ...actual,
    loadProviderKey: loadMock,
    saveProviderKey: saveMock,
    deleteProviderKey: deleteMock,
  }
})

const SAVED = {
  provider: 'openrouter' as const,
  key_hint: 'd7bd',
  verified_at: '2026-09-17T15:22:45Z',
  created_at: '2026-09-17T15:22:45Z',
  label: null,
}

beforeEach(() => {
  loadMock.mockReset()
  saveMock.mockReset()
  deleteMock.mockReset()
  loadMock.mockResolvedValue(null)
  saveMock.mockResolvedValue(SAVED)
  deleteMock.mockResolvedValue(undefined)
})

describe('the company provider key', () => {
  test('a company with no key is told that nothing can run without one', async () => {
    render(<ProviderKeyCard />)

    expect(await screen.findByText('No key saved')).toBeInTheDocument()
    expect(screen.getByText(/cannot upload documents or start a bid/)).toBeInTheDocument()
  })

  test('a saved key is shown by its last four characters and nothing more', async () => {
    loadMock.mockResolvedValue(SAVED)

    render(<ProviderKeyCard />)

    expect(await screen.findByText('…d7bd')).toBeInTheDocument()
    expect(screen.getByText(/OpenRouter key in use/)).toBeInTheDocument()
  })

  test('the field never reveals what is typed into it', async () => {
    render(<ProviderKeyCard />)

    const field = await screen.findByLabelText('OpenRouter key')

    expect(field).toHaveAttribute('type', 'password')
    expect(field).toHaveAttribute('autocomplete', 'off')
  })

  test('saving sends the key once and shows what came back', async () => {
    const user = userEvent.setup()
    render(<ProviderKeyCard />)

    await user.type(await screen.findByLabelText('OpenRouter key'), 'sk-or-v1-abcd')
    await user.click(screen.getByRole('button', { name: 'Save key' }))

    await waitFor(() => expect(saveMock).toHaveBeenCalledWith('sk-or-v1-abcd'))
    expect(await screen.findByText('…d7bd')).toBeInTheDocument()
  })

  test('the field is cleared after a save, so the key is not left on the screen', async () => {
    const user = userEvent.setup()
    render(<ProviderKeyCard />)

    const field = await screen.findByLabelText('OpenRouter key')
    await user.type(field, 'sk-or-v1-abcd')
    await user.click(screen.getByRole('button', { name: 'Save key' }))

    await waitFor(() => expect(screen.getByLabelText('Replace the key')).toHaveValue(''))
  })

  test("a key the provider refuses shows the provider's own reason", async () => {
    const user = userEvent.setup()
    saveMock.mockRejectedValue(new Error('OpenRouter refused this key.'))
    render(<ProviderKeyCard />)

    await user.type(await screen.findByLabelText('OpenRouter key'), 'sk-or-v1-wrong')
    await user.click(screen.getByRole('button', { name: 'Save key' }))

    expect(await screen.findByText(/OpenRouter refused this key/)).toBeInTheDocument()
  })

  test('nothing can be saved until something is typed', async () => {
    render(<ProviderKeyCard />)

    expect(await screen.findByRole('button', { name: 'Save key' })).toBeDisabled()
  })

  test('removing the key puts the company back to having none', async () => {
    const user = userEvent.setup()
    loadMock.mockResolvedValue(SAVED)
    render(<ProviderKeyCard />)

    await user.click(await screen.findByRole('button', { name: 'Remove key' }))

    await waitFor(() => expect(deleteMock).toHaveBeenCalled())
    expect(await screen.findByText('No key saved')).toBeInTheDocument()
  })
})
