// SPDX-License-Identifier: Apache-2.0
export interface Preset {
  id: string
  label: string
  family: 'openai_compat' | 'anthropic' | 'google'
  default_base_url: string
  default_headers: Record<string, string>
  api_key_required: boolean
  api_key_env: string | null
  model_list_url_suffix: string | null
  test_url_suffix: string | null
  deferred: boolean
  icon: string
  homepage: string
  order: number
}