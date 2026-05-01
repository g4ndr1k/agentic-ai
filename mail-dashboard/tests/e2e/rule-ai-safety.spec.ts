import { expect, test, type Page, type Route } from '@playwright/test';

const account = {
  id: 'gmail_g4ndr1k',
  name: 'g4ndr1k',
  email: 'g4ndr1k@example.com',
  provider: 'gmail',
  enabled: true,
  status: 'active',
  last_success_at: null,
  last_error: null,
};

const aiSettings = {
  enabled: false,
  provider: 'ollama',
  base_url: 'http://127.0.0.1:11434',
  model: 'qwen2.5:7b-instruct-q4_K_M',
  temperature: 0,
  timeout_seconds: 30,
  max_body_chars: 12000,
  urgency_threshold: 8,
};

type ApiMocks = {
  draftResponse?: unknown;
  goldenProbeResponse?: unknown;
  explainResponse?: unknown;
  qualitySummary?: unknown;
  qualityRecent?: unknown[];
  rules?: unknown[];
};

async function installMailApiMocks(page: Page, mocks: ApiMocks = {}) {
  const saveRuleBodies: unknown[] = [];
  const unmockedRequests: string[] = [];

  await page.route('**/api/mail/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    const fulfillJson = (body: unknown, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (method === 'GET' && path === '/api/mail/summary') {
      return fulfillJson({
        total_processed: 0,
        urgent_count: 0,
        drafts_created: 0,
        avg_priority: 0,
        source_split: { gmail: 0, outlook: 0 },
        classification: {},
        actions: {
          drafts_created: 0,
          labels_applied: 0,
          imessage_alerts: 0,
          important_count: 0,
          reply_needed_count: 0,
        },
        mode: 'draft_only',
      });
    }
    if (method === 'GET' && path === '/api/mail/recent') return fulfillJson({ items: [] });
    if (method === 'GET' && path === '/api/mail/accounts') return fulfillJson({ accounts: [account] });
    if (method === 'GET' && path === '/api/mail/rules') return fulfillJson(mocks.rules ?? []);
    if (method === 'GET' && path === '/api/mail/processing-events') return fulfillJson([]);
    if (method === 'GET' && path === '/api/mail/ai/settings') return fulfillJson(aiSettings);
    if (method === 'GET' && path === '/api/mail/ai/triggers') return fulfillJson([]);
    if (method === 'GET' && path === '/api/mail/rules/ai/audit/summary') {
      return fulfillJson(mocks.qualitySummary ?? {
        total_draft_attempts: 0,
        saveable_count: 0,
        unsupported_count: 0,
        failed_count: 0,
        saveable_rate: 0,
        by_mode: {},
        by_safety_status: {},
        latest_golden_probe: null,
      });
    }
    if (method === 'GET' && path === '/api/mail/rules/ai/audit/recent') {
      return fulfillJson({ items: mocks.qualityRecent ?? [] });
    }
    if (method === 'GET' && path === '/api/mail/rules/ai/golden-probe/runs') {
      return fulfillJson({ items: [] });
    }
    if (method === 'POST' && path === '/api/mail/rules/ai/draft') {
      return fulfillJson(mocks.draftResponse ?? unsupportedDraft());
    }
    if (method === 'POST' && path === '/api/mail/rules/ai/golden-probe') {
      return fulfillJson(mocks.goldenProbeResponse ?? disabledGoldenProbe());
    }
    if (method === 'POST' && path === '/api/mail/rules/explain') {
      return fulfillJson(mocks.explainResponse ?? explainResponse());
    }
    if (method === 'POST' && path === '/api/mail/rules') {
      const body = request.postDataJSON();
      saveRuleBodies.push(body);
      return fulfillJson({
        ...body,
        rule_id: 12,
        created_at: '2026-05-02T00:00:00Z',
        updated_at: '2026-05-02T00:00:00Z',
      });
    }

    unmockedRequests.push(`${method} ${path}`);
    return fulfillJson({ detail: `Unmocked API request: ${method} ${path}` }, 599);
  });

  return { saveRuleBodies, unmockedRequests };
}

async function openSettings(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Settings' }).click();
  await expect(page.getByRole('heading', { name: 'Rules' })).toBeVisible();
}

function saveableSuppressionDraft() {
  return {
    intent_summary: 'Suppress alerts from abcd@efcf.com',
    confidence: 0.95,
    status: 'draft',
    saveable: true,
    safety_status: 'safe_local_suppression',
    requires_user_confirmation: true,
    provider: 'ollama',
    model: 'qwen2.5:7b-instruct-q4_K_M',
    explanation: ['This creates a local Mail Agent suppression rule.'],
    warnings: [
      'This does not mutate Gmail.',
      'This does not move messages to Gmail Spam.',
    ],
    rule: {
      account_id: null,
      name: 'Suppress sender abcd@efcf.com',
      match_type: 'ALL',
      conditions: [
        { field: 'from_email', operator: 'equals', value: 'abcd@efcf.com' },
      ],
      actions: [
        { action_type: 'skip_ai_inference', target: null, value_json: null, stop_processing: false },
        { action_type: 'stop_processing', target: null, value_json: null, stop_processing: true },
      ],
    },
  };
}

function unsupportedDraft() {
  return {
    intent_summary: 'Unsupported draft',
    confidence: 0,
    status: 'unsupported',
    saveable: false,
    safety_status: 'llm_draft_failed',
    requires_user_confirmation: true,
    rule: null,
    explanation: [],
    warnings: [
      'The local model did not produce a safe rule draft.',
      'No rule was saved.',
    ],
  };
}

function disabledGoldenProbe() {
  return {
    status: 'disabled',
    summary: { total: 2, passed: 0, failed: 0, skipped: 2 },
    rule_ai: {
      enabled: false,
      provider: 'ollama',
      model: 'qwen2.5:7b-instruct-q4_K_M',
    },
    results: [],
    warnings: ['Local Rule AI is disabled.'],
    safety: {
      saved_rules: false,
      sent_imessage: false,
      mutated_gmail: false,
      mutated_imap: false,
    },
  };
}

function mixedGoldenProbe() {
  return {
    status: 'failed',
    summary: { total: 2, passed: 1, failed: 1, skipped: 0 },
    rule_ai: {
      enabled: true,
      provider: 'ollama',
      model: 'qwen2.5:7b-instruct-q4_K_M',
    },
    results: [
      {
        id: 'bca_suspicious',
        prompt: 'If BCA sends suspicious transaction alert, notify me.',
        passed: true,
        expected_domain: 'bca.co.id',
        actual_domain: 'bca.co.id',
        errors: [],
        warnings: [],
      },
      {
        id: 'cimb_confirmation',
        prompt: 'If CIMB asks for confirmation, notify me.',
        passed: false,
        expected_domain: 'cimbniaga.co.id',
        actual_domain: null,
        errors: ['missing_sender_condition'],
        warnings: [],
      },
    ],
    warnings: [],
    safety: {
      saved_rules: false,
      sent_imessage: false,
      mutated_gmail: false,
      mutated_imap: false,
    },
  };
}

function explainResponse() {
  return {
    status: 'ok',
    preview: true,
    message_summary: {
      sender_email: 'alerts@bca.co.id',
      sender_domain: 'bca.co.id',
      subject: 'Suspicious transaction alert',
      account_id: 'gmail_g4ndr1k',
    },
    matched_rule_count: 1,
    stopped: true,
    would_skip_ai: true,
    enqueue_ai: false,
    continue_to_classifier: true,
    route_to_pdf_pipeline: false,
    planned_actions: [
      {
        rule_id: 12,
        action_type: 'mark_pending_alert',
        target: 'imessage',
        value: { template: 'BCA suspicious transaction email detected.' },
        mutation: false,
        would_execute: false,
        explanation: 'Would queue a local pending alert only after the saved rule runs in normal processing.',
      },
      {
        rule_id: 13,
        action_type: 'skip_ai_inference',
        target: null,
        value: null,
        mutation: false,
        would_execute: false,
        explanation: 'Would skip local AI inference for this message during normal processing.',
      },
    ],
    rules: [
      {
        rule_id: 12,
        name: 'BCA suspicious transaction alert',
        matched: true,
        conditions: [
          {
            field: 'from_domain',
            operator: 'contains',
            expected: 'bca.co.id',
            actual: 'bca.co.id',
            matched: true,
            case_sensitive: false,
          },
          {
            field: 'subject',
            operator: 'contains',
            expected: 'suspicious',
            actual: 'Suspicious transaction alert',
            matched: true,
            case_sensitive: false,
          },
        ],
        planned_actions: [],
      },
    ],
    safety: {
      read_only: true,
      sent_imessage: false,
      called_bridge: false,
      called_imap: false,
      mutated_gmail: false,
      mutated_imap: false,
      wrote_events: false,
    },
  };
}

test('sender suppression draft strips AI metadata before human Save Rule', async ({ page }) => {
  const api = await installMailApiMocks(page, {
    draftResponse: saveableSuppressionDraft(),
  });
  await openSettings(page);

  const builder = page.getByTestId('ai-rule-builder');
  await builder.locator('textarea').fill('Add abcd@efcf.com to the spam list');
  await builder.getByRole('button', { name: 'Draft Rule' }).click();

  await expect(builder.getByText('AI Rule Draft').first()).toBeVisible();
  await expect(builder.getByText('Safe Local Suppression').first()).toBeVisible();
  await expect(builder.getByText('This does not mutate Gmail').first()).toBeVisible();
  await expect(builder.getByText('This does not move messages to Gmail Spam.')).toBeVisible();

  await builder.getByRole('button', { name: 'Save Rule' }).click();
  await expect.poll(() => api.saveRuleBodies.length).toBe(1);
  expect(api.unmockedRequests).toEqual([]);

  const body = api.saveRuleBodies[0] as Record<string, unknown>;
  expect(Object.keys(body).sort()).toEqual([
    'account_id',
    'actions',
    'conditions',
    'enabled',
    'match_type',
    'name',
    'priority',
  ]);
  expect(body).toMatchObject({
    name: 'Suppress sender abcd@efcf.com',
    account_id: null,
    match_type: 'ALL',
    priority: 10,
    enabled: true,
  });
  for (const key of [
    'status',
    'saveable',
    'safety_status',
    'warnings',
    'explanation',
    'provider',
    'model',
    'raw_model_error',
  ]) {
    expect(body).not.toHaveProperty(key);
  }
});

test('unsupported draft hides Save Rule and does not call create rule', async ({ page }) => {
  const api = await installMailApiMocks(page, {
    draftResponse: unsupportedDraft(),
  });
  await openSettings(page);

  const builder = page.getByTestId('ai-rule-builder');
  await builder.locator('textarea').fill('Move everything suspicious to spam automatically');
  await builder.getByRole('button', { name: 'Draft Rule' }).click();

  await expect(builder.getByText('Local model could not create a safe draft. No rule was saved.')).toBeVisible();
  await expect(builder.getByText('The local model did not produce a safe rule draft.')).toBeVisible();
  await expect(builder.getByRole('button', { name: 'Save Rule' })).toHaveCount(0);
  await builder.getByRole('button', { name: 'Draft Rule' }).click();
  expect(api.saveRuleBodies).toHaveLength(0);
  expect(api.unmockedRequests).toEqual([]);
});

test('golden probe disabled state is safe and has no save control', async ({ page }) => {
  const api = await installMailApiMocks(page, {
    goldenProbeResponse: disabledGoldenProbe(),
  });
  await openSettings(page);

  const probe = page.getByTestId('rule-ai-golden-probe');
  await probe.getByRole('button', { name: 'Run Golden Probe' }).click();

  await expect(probe.getByText('Rule AI golden probe disabled')).toBeVisible();
  await expect(probe.getByText('[mail.rule_ai].enabled is false')).toBeVisible();
  await expect(probe.getByRole('button', { name: 'Save Rule' })).toHaveCount(0);
  expect(api.unmockedRequests).toEqual([]);
});

test('golden probe renders pass/fail summary without save controls', async ({ page }) => {
  const api = await installMailApiMocks(page, {
    goldenProbeResponse: mixedGoldenProbe(),
  });
  await openSettings(page);

  const probe = page.getByTestId('rule-ai-golden-probe');
  await probe.getByRole('button', { name: 'Run Golden Probe' }).click();

  await expect(probe.getByText('Rule AI golden probe failed')).toBeVisible();
  await expect(probe.getByText('1 passed / 1 failed / 2 total')).toBeVisible();
  await expect(probe.getByText('ollama / qwen2.5:7b-instruct-q4_K_M')).toBeVisible();
  await expect(probe.getByText('missing_sender_condition')).toBeVisible();
  await expect(probe.getByRole('button', { name: 'Save Rule' })).toHaveCount(0);
  expect(api.unmockedRequests).toEqual([]);
});

test('Rule AI Quality panel renders privacy-safe audit metrics only', async ({ page }) => {
  const api = await installMailApiMocks(page, {
    qualitySummary: {
      total_draft_attempts: 10,
      saveable_count: 7,
      unsupported_count: 2,
      failed_count: 1,
      saveable_rate: 0.7,
      by_mode: { sender_suppression: 5, alert_rule: 5 },
      by_safety_status: { safe_local_suppression: 5, safe_local_alert_draft: 2 },
      latest_golden_probe: {
        id: 4,
        created_at: '2026-05-02T00:00:00Z',
        status: 'failed',
        total: 2,
        passed: 1,
        failed: 1,
        skipped: 0,
        provider: 'ollama',
        model: 'qwen2.5:7b-instruct-q4_K_M',
        duration_ms: 1200,
        results: [],
      },
    },
    qualityRecent: [
      {
        id: 44,
        created_at: '2026-05-02T00:00:00Z',
        mode: 'alert_rule',
        status: 'draft',
        saveable: true,
        safety_status: 'safe_local_alert_draft',
        provider: 'ollama',
        model: 'qwen2.5:7b-instruct-q4_K_M',
        request_hash: 'abc123',
        request_preview: 'If BCA sends suspicious transaction alert',
        rule_name: 'BCA suspicious transaction alert',
        condition_count: 2,
        action_count: 1,
        source: 'draft_endpoint',
      },
    ],
  });
  await openSettings(page);

  const quality = page.getByTestId('rule-ai-quality');
  await expect(quality.getByText('Audit stores request hashes and short previews only')).toBeVisible();
  await expect(quality.getByText('It does not store raw model output or save rules')).toBeVisible();
  await expect(quality.getByText('Draft attempts', { exact: true })).toBeVisible();
  await expect(quality.getByText('10')).toBeVisible();
  await expect(quality.getByText('Saveable rate')).toBeVisible();
  await expect(quality.getByText('70%')).toBeVisible();
  await expect(quality.getByText('Latest golden probe: 1 passed / 1 failed / 2 total')).toBeVisible();
  await expect(quality.getByText('Recent AI draft attempts')).toBeVisible();
  await expect(quality.getByText('If BCA sends suspicious transaction alert')).toBeVisible();
  await expect(quality.getByRole('button', { name: /save|rerun|execute/i })).toHaveCount(0);
  expect(api.unmockedRequests).toEqual([]);
});

test('Explain Rule dry-run panel renders deterministic explanation and safety copy', async ({ page }) => {
  const api = await installMailApiMocks(page, {
    explainResponse: explainResponse(),
  });
  await openSettings(page);

  const panel = page.getByTestId('rule-explain-panel');
  await panel.locator('textarea').fill(JSON.stringify({
    sender_email: 'alerts@bca.co.id',
    subject: 'Suspicious transaction alert',
    body_text: 'We detected suspicious transaction activity.',
    imap_account: 'gmail_g4ndr1k',
    imap_folder: 'INBOX',
    has_attachment: false,
  }, null, 2));
  await panel.getByRole('button', { name: 'Run Dry-Run Explanation' }).click();

  await expect(panel.getByText('matched').first()).toBeVisible();
  await expect(panel.getByText('from_domain')).toBeVisible();
  await expect(panel.getByText('bca.co.id').first()).toBeVisible();
  await expect(panel.getByText('actual:').first()).toBeVisible();
  await expect(panel.getByText('Mark pending alert')).toBeVisible();
  await expect(panel.getByText('would_skip_ai')).toBeVisible();
  await expect(panel.getByText('stopped')).toBeVisible();
  await expect(panel.getByText('Dry-run only', { exact: true })).toBeVisible();
  await expect(panel.getByText('No iMessage', { exact: true })).toBeVisible();
  await expect(panel.getByText('No Gmail mutation', { exact: true })).toBeVisible();
  await expect(panel.getByText('No IMAP call', { exact: true })).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Save Rule' })).toHaveCount(0);
  expect(api.unmockedRequests).toEqual([]);
});
