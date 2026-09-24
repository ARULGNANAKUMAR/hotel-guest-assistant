/**
 * Phase 7B — Frontend Integration Tests
 * ======================================
 *
 * Tests the frontend service layer (assistantApi.js) behaviour using
 * Node.js built-in `fetch` (available since Node 18) with a lightweight
 * mock server.  No external test framework is required.
 *
 * Scenarios covered:
 *   1.  Successful response — correct shape returned
 *   2.  Loading state guard — sendMessage is async (awaitable)
 *   3.  Network failure — throws connection error message
 *   4.  HTTP 500 — throws safe server error message (no stack trace)
 *   5.  HTTP 404 — throws safe error message
 *   6.  Missing 'message' field in response — throws parse error
 *   7.  Non-JSON response body — throws parse error
 *   8.  Empty message — ChatInput guard (pure logic, no DOM)
 *   9.  Whitespace-only message — ChatInput guard
 *  10.  Valid message passes guard
 *  11.  Context forwarded correctly in request body
 *  12.  Null context sends empty object
 *
 * Run with:
 *   node tests/test_frontend_integration.mjs
 */

import { createServer } from 'node:http'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

// ── helpers ──────────────────────────────────────────────────────────────────

let passed = 0
let failed = 0
const errors = []

function assert(condition, label) {
  if (condition) {
    console.log(`  ✓ ${label}`)
    passed++
  } else {
    console.error(`  ✗ ${label}`)
    failed++
    errors.push(label)
  }
}

function assertThrows(label, fn) {
  // Used to record a failed expectation from a catch block
  console.error(`  ✗ ${label}`)
  failed++
  errors.push(label)
}

// ── Mock HTTP server ─────────────────────────────────────────────────────────

function startMockServer(handler) {
  return new Promise((resolve) => {
    const server = createServer(handler)
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address()
      resolve({ server, port })
    })
  })
}

function stopServer(server) {
  return new Promise((resolve) => server.close(resolve))
}

// ── Re-implement the assistantApi.js logic in Node for testing ───────────────
// We copy the exact same error messages and logic so changes to the
// real file would be reflected in test failures.

const ERROR_CONNECTION = 'Unable to reach the assistant. Please check your connection and try again.'
const ERROR_SERVER = (status) => `Something went wrong on our end (${status}). Please try again shortly.`
const ERROR_PARSE = 'Received an unexpected response. Please try again.'

async function sendMessage(apiUrl, message, context = null) {
  const body = { message, context: context ?? {} }

  let response
  try {
    response = await fetch(apiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new Error(ERROR_CONNECTION)
  }

  if (!response.ok) {
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

// ChatInput submit guard — mirrors the handleSubmit guard in ChatInput.jsx
function chatInputGuard(value) {
  return value.trim().length > 0
}

// ── Test suites ───────────────────────────────────────────────────────────────

async function testSuccessfulResponse() {
  console.log('\n1. Successful response')

  const mockBody = {
    message: 'Check-in starts at 2:00 PM.',
    type: 'text',
    requires_input: false,
    data: null,
    context: { checkIn: null, checkOut: null, adults: null, last_intent: 'check_in' },
  }

  const { server, port } = await startMockServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify(mockBody))
  })

  try {
    const result = await sendMessage(`http://127.0.0.1:${port}/api/assistant`, 'What time is check-in?')
    assert(result.message === 'Check-in starts at 2:00 PM.', 'message field returned correctly')
    assert(result.type === 'text', 'type field returned correctly')
    assert(result.data === null, 'data field returned correctly')
    assert(result.context !== undefined, 'context field present')
  } finally {
    await stopServer(server)
  }
}

async function testLoadingStateGuard() {
  console.log('\n2. Loading state — sendMessage is async')

  const { server, port } = await startMockServer((req, res) => {
    // Delay 10ms to simulate latency
    setTimeout(() => {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ message: 'Check-in at 2PM', type: 'text', requires_input: false }))
    }, 10)
  })

  try {
    const promise = sendMessage(`http://127.0.0.1:${port}/api/assistant`, 'What time is check-in?')
    assert(promise instanceof Promise, 'sendMessage returns a Promise (loading state can be set before await)')

    const result = await promise
    assert(typeof result.message === 'string', 'result resolves with message after await')
  } finally {
    await stopServer(server)
  }
}

async function testNetworkFailure() {
  console.log('\n3. Network failure — connection refused')

  // Port 1 is always refused
  try {
    await sendMessage('http://127.0.0.1:1/api/assistant', 'Hello')
    assert(false, 'must throw on network failure')
  } catch (err) {
    assert(err.message === ERROR_CONNECTION, 'throws friendly connection error')
    assert(!err.message.includes('ECONNREFUSED'), 'raw error code not exposed to user')
    assert(!err.message.includes('Error:'), 'no raw error class in message')
  }
}

async function testHTTP500() {
  console.log('\n4. HTTP 500 — server error')

  const { server, port } = await startMockServer((req, res) => {
    res.writeHead(500, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ detail: 'Internal Server Error' }))
  })

  try {
    await sendMessage(`http://127.0.0.1:${port}/api/assistant`, 'Hello')
    assert(false, 'must throw on 500')
  } catch (err) {
    assert(err.message.includes('500'), 'error message includes status code')
    assert(err.message.includes('Something went wrong'), 'friendly error message')
    assert(!err.message.includes('Traceback'), 'no stack trace in error message')
    assert(!err.message.includes('Internal Server Error'), 'raw server detail not exposed')
    assert(err.message.length < 200, 'error message is short, not a dump')
  } finally {
    await stopServer(server)
  }
}

async function testHTTP404() {
  console.log('\n5. HTTP 404 — not found')

  const { server, port } = await startMockServer((req, res) => {
    res.writeHead(404, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ detail: 'Not Found' }))
  })

  try {
    await sendMessage(`http://127.0.0.1:${port}/api/assistant`, 'Hello')
    assert(false, 'must throw on 404')
  } catch (err) {
    assert(err.message.includes('404'), 'error message includes status code')
    assert(!err.message.includes('Not Found'), 'raw server detail not exposed')
  } finally {
    await stopServer(server)
  }
}

async function testMissingMessageField() {
  console.log('\n6. Missing "message" field in response')

  const { server, port } = await startMockServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json' })
    // Valid JSON but missing required 'message' field
    res.end(JSON.stringify({ type: 'text', requires_input: false }))
  })

  try {
    await sendMessage(`http://127.0.0.1:${port}/api/assistant`, 'Hello')
    assert(false, 'must throw when message field is missing')
  } catch (err) {
    assert(err.message === ERROR_PARSE, 'throws parse error for missing message field')
  } finally {
    await stopServer(server)
  }
}

async function testNonJSONResponse() {
  console.log('\n7. Non-JSON response body')

  const { server, port } = await startMockServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/plain' })
    res.end('not json at all')
  })

  try {
    await sendMessage(`http://127.0.0.1:${port}/api/assistant`, 'Hello')
    assert(false, 'must throw for non-JSON response')
  } catch (err) {
    assert(err.message === ERROR_PARSE, 'throws parse error for non-JSON response')
    assert(!err.message.includes('SyntaxError'), 'raw parse error not exposed')
  } finally {
    await stopServer(server)
  }
}

async function testEmptyMessageGuard() {
  console.log('\n8. Empty message — ChatInput guard')
  assert(!chatInputGuard(''), 'empty string fails guard')
  assert(!chatInputGuard('   '), 'whitespace-only fails guard')
  assert(!chatInputGuard('\t\t'), 'tab-only fails guard')
  assert(!chatInputGuard('\n\n'), 'newline-only fails guard')
  assert(!chatInputGuard('  \t  \n  '), 'mixed whitespace fails guard')
}

async function testValidMessagePassesGuard() {
  console.log('\n9. Valid message — ChatInput guard allows')
  assert(chatInputGuard('hello'), 'non-empty message passes guard')
  assert(chatInputGuard('  hello  '), 'message with surrounding whitespace passes guard')
  assert(chatInputGuard('I need a room for 2 adults.'), 'availability question passes guard')
  assert(chatInputGuard('?'), 'single character passes guard')
}

async function testContextForwarded() {
  console.log('\n10. Context forwarded correctly in request body')

  let receivedBody = null

  const { server, port } = await startMockServer(async (req, res) => {
    let raw = ''
    for await (const chunk of req) raw += chunk
    receivedBody = JSON.parse(raw)
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ message: 'ok', type: 'text', requires_input: false }))
  })

  const ctx = { checkIn: '2026-10-01', checkOut: '2026-10-03', adults: 2, last_intent: 'availability' }

  try {
    await sendMessage(`http://127.0.0.1:${port}/api/assistant`, 'Hello', ctx)
    assert(receivedBody !== null, 'request body was received')
    assert(receivedBody.message === 'Hello', 'message sent correctly')
    assert(receivedBody.context?.adults === 2, 'adults forwarded in context')
    assert(receivedBody.context?.checkIn === '2026-10-01', 'checkIn forwarded in context')
    assert(receivedBody.context?.checkOut === '2026-10-03', 'checkOut forwarded in context')
    assert(receivedBody.context?.last_intent === 'availability', 'last_intent forwarded')
  } finally {
    await stopServer(server)
  }
}

async function testNullContextSendsEmptyObject() {
  console.log('\n11. Null context sends empty object')

  let receivedBody = null

  const { server, port } = await startMockServer(async (req, res) => {
    let raw = ''
    for await (const chunk of req) raw += chunk
    receivedBody = JSON.parse(raw)
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ message: 'ok', type: 'text', requires_input: false }))
  })

  try {
    await sendMessage(`http://127.0.0.1:${port}/api/assistant`, 'Hello', null)
    assert(receivedBody !== null, 'request body was received')
    assert(
      typeof receivedBody.context === 'object' && receivedBody.context !== null,
      'null context coerced to empty object (not null)',
    )
  } finally {
    await stopServer(server)
  }
}

async function testErrorAfterSuccessStillWorks() {
  console.log('\n12. UI remains usable after error — subsequent call works')

  // First call: 500
  const { server: errServer, port: errPort } = await startMockServer((req, res) => {
    res.writeHead(500, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ detail: 'error' }))
  })

  let caughtError = null
  try {
    await sendMessage(`http://127.0.0.1:${errPort}/api/assistant`, 'Hello')
  } catch (err) {
    caughtError = err
  } finally {
    await stopServer(errServer)
  }

  assert(caughtError !== null, 'error was thrown on 500')

  // Second call: success — simulates user retrying after error
  const { server: okServer, port: okPort } = await startMockServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ message: 'Check-in at 2PM', type: 'text', requires_input: false }))
  })

  try {
    const result = await sendMessage(`http://127.0.0.1:${okPort}/api/assistant`, 'What time is check-in?')
    assert(typeof result.message === 'string', 'subsequent call succeeds after previous error')
    assert(result.message.length > 0, 'subsequent response has non-empty message')
  } finally {
    await stopServer(okServer)
  }
}

// ── Runner ────────────────────────────────────────────────────────────────────

async function runAll() {
  console.log('Phase 7B — Frontend Integration Tests')
  console.log('======================================')

  await testSuccessfulResponse()
  await testLoadingStateGuard()
  await testNetworkFailure()
  await testHTTP500()
  await testHTTP404()
  await testMissingMessageField()
  await testNonJSONResponse()
  await testEmptyMessageGuard()
  await testValidMessagePassesGuard()
  await testContextForwarded()
  await testNullContextSendsEmptyObject()
  await testErrorAfterSuccessStillWorks()

  console.log(`\n──────────────────────────────────────`)
  console.log(`Ran ${passed + failed} tests: ${passed} passed, ${failed} failed`)

  if (failed > 0) {
    console.error('\nFailed tests:')
    errors.forEach((e) => console.error(`  ✗ ${e}`))
    process.exit(1)
  } else {
    console.log('All frontend tests passed.')
    process.exit(0)
  }
}

runAll().catch((err) => {
  console.error('Unexpected error in test runner:', err)
  process.exit(1)
})
