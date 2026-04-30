import assert from 'node:assert/strict';
import test from 'node:test';

import {
  RULE_ACTIONS,
  actionLabel,
  actionRequiresTarget,
  accountOptionLabel,
  accountScopeLabel,
  defaultRuleAccountId,
  hasPriorityConflict,
  isMutationAction,
  reorderPayloadForScope,
  rulePayloadWithAccountScope,
} from '../src/views/ruleUiHelpers.ts';

const accounts = [
  {
    id: 'acct_g4ndr1k',
    name: 'g4ndr1k',
    email: 'g4ndr1k@gmail.com',
    provider: 'gmail',
    enabled: true,
    status: 'active',
    last_success_at: null,
    last_error: null,
  },
  {
    id: 'acct_dian',
    name: 'Dian Pratiwi',
    email: 'dian@example.com',
    provider: 'gmail',
    enabled: true,
    status: 'active',
    last_success_at: null,
    last_error: null,
  },
  {
    id: 'acct_disabled',
    name: 'Disabled',
    email: 'disabled@example.com',
    provider: 'gmail',
    enabled: false,
    status: 'active',
    last_success_at: null,
    last_error: null,
  },
];

const baseRule = {
  account_id: 'acct_g4ndr1k',
  name: 'Statements',
  priority: 10,
  enabled: true,
  match_type: 'ALL' as const,
  conditions: [],
  actions: [],
};

const rules = [
  { ...baseRule, rule_id: 1, created_at: '', updated_at: '', account_id: 'acct_g4ndr1k', priority: 10 },
  { ...baseRule, rule_id: 2, created_at: '', updated_at: '', account_id: 'acct_g4ndr1k', priority: 20 },
  { ...baseRule, rule_id: 3, created_at: '', updated_at: '', account_id: 'acct_dian', priority: 10 },
  { ...baseRule, rule_id: 4, created_at: '', updated_at: '', account_id: null, priority: 10 },
  { ...baseRule, rule_id: 5, created_at: '', updated_at: '', account_id: null, priority: 20 },
];

test('create account-scoped rule defaults to the first active account', () => {
  assert.equal(defaultRuleAccountId(accounts), 'acct_g4ndr1k');
  assert.equal(rulePayloadWithAccountScope(baseRule, 'acct_g4ndr1k').account_id, 'acct_g4ndr1k');
});

test('create global rule is explicit', () => {
  assert.equal(rulePayloadWithAccountScope(baseRule, null).account_id, null);
});

test('edit account scope can move between accounts', () => {
  assert.equal(defaultRuleAccountId(accounts, 'acct_dian'), 'acct_dian');
  assert.equal(rulePayloadWithAccountScope(baseRule, 'acct_dian').account_id, 'acct_dian');
});

test('duplicate priority fails only within the same account scope', () => {
  assert.equal(hasPriorityConflict(rules, 'acct_g4ndr1k', 10), true);
  assert.equal(hasPriorityConflict(rules, 'acct_dian', 20), false);
  assert.equal(hasPriorityConflict(rules, null, 20), true);
  assert.equal(hasPriorityConflict(rules, null, 10, 4), false);
});

test('rules list displays account labels correctly', () => {
  assert.equal(accountScopeLabel(null, accounts), 'Global');
  assert.equal(accountScopeLabel('acct_g4ndr1k', accounts), 'g4ndr1k');
  assert.equal(accountScopeLabel('acct_dian', accounts), 'Dian Pratiwi');
  assert.equal(accountOptionLabel(accounts[1]), 'Dian Pratiwi — dian@example.com');
});

test('reorder payload is scoped to one account', () => {
  assert.deepEqual(reorderPayloadForScope(rules, 2, -1), [
    { rule_id: 2, priority: 10 },
    { rule_id: 1, priority: 20 },
  ]);
  assert.deepEqual(reorderPayloadForScope(rules, 5, -1), [
    { rule_id: 5, priority: 10 },
    { rule_id: 4, priority: 20 },
  ]);
});

test('safe mutation actions are exposed with target rules', () => {
  assert.equal(RULE_ACTIONS.includes('move_to_folder' as any), true);
  assert.equal(RULE_ACTIONS.includes('mark_read' as any), true);
  assert.equal(actionLabel('move_to_folder'), 'Move to folder');
  assert.equal(isMutationAction('mark_flagged'), true);
  assert.equal(actionRequiresTarget('move_to_folder'), true);
  assert.equal(actionRequiresTarget('mark_read'), false);
});

test('dangerous actions are not exposed', () => {
  const forbidden = [
    'add_label',
    'send_imessage',
    'delete',
    'expunge',
    'auto_reply',
    'forward',
    'unsubscribe',
    'external_webhook',
  ];
  for (const action of forbidden) {
    assert.equal(RULE_ACTIONS.includes(action as any), false, action);
  }
});
