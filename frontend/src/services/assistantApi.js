/**
 * assistantApi.js
 * Sends guest message + context to POST /api/assistant.
 * Returns { message, type, data, context }.
 */

const API_URL = '/api/assistant'

const ERROR_CONNECTION = 'Unable to reach the assistant. Please check your connection and try again.'
const ERROR_SERVER = (status) => `Something went wrong on our end (${status}). Please try again shortly.`
const ERROR_PARSE = 'Received an unexpected response. Please try again.'

export async function sendMessage(message, context = null) {
  const body = { message, context: context ?? {} }

  let response
  try {
    response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new Error(ERROR_CONNECTION)
  }

  if (!response.ok) {
    // Don't surface raw backend detail — use a generic safe message
    throw new Error(ERROR_SERVER(response.status))
  }

  let data
  try {
    data = await response.json()
  } catch {
    throw new Error(ERROR_PARSE)
  }

  if (!data?.message) {
    throw new Error(ERROR_PARSE)
  }

  return {
    message: data.message,
    type: data.type ?? 'text',
    data: data.data ?? null,
    context: data.context ?? null,
  }
}
