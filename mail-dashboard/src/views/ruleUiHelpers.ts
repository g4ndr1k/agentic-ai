import type { AccountHealth, MailRule, MailRuleInput } from '../api/mail';

export const PHASE_4A_SAFE_ACTIONS = [
  'mark_pending_alert',
  'skip_ai_inference',
  'add_to_needs_reply',
  'route_to_pdf_pipeline',
  'notify_dashboard',
  'stop_processing',
] as const;

export function activeRuleAccounts(accounts: AccountHealth[]) {
  return accounts.filter((account) => account.enabled !== false && account.status === 'active');
}

export function accountOptionLabel(account: AccountHealth) {
  return `${account.name} — ${account.email}`;
}

export function ruleScopeKey(accountId: string | null | undefined) {
  return accountId ?? '__global__';
}

export function defaultRuleAccountId(accounts: AccountHealth[], selectedAccountId?: string | null) {
  const activeAccounts = activeRuleAccounts(accounts);
  if (selectedAccountId && activeAccounts.some((account) => account.id === selectedAccountId)) {
    return selectedAccountId;
  }
  return activeAccounts[0]?.id ?? null;
}

export function accountScopeLabel(accountId: string | null | undefined, accounts: AccountHealth[]) {
  if (accountId == null) return 'Global';
  return accounts.find((account) => account.id === accountId)?.name ?? accountId;
}

export function rulesInScope(rules: MailRule[], accountId: string | null | undefined) {
  const scope = ruleScopeKey(accountId);
  return rules
    .filter((rule) => ruleScopeKey(rule.account_id) === scope)
    .sort((a, b) => a.priority - b.priority || a.rule_id - b.rule_id);
}

export function nextPriorityForScope(rules: MailRule[], accountId: string | null | undefined) {
  const scoped = rulesInScope(rules, accountId);
  const maxPriority = scoped.reduce((max, rule) => Math.max(max, rule.priority), 0);
  return maxPriority + 10;
}

export function hasPriorityConflict(
  rules: MailRule[],
  accountId: string | null | undefined,
  priority: number,
  ignoreRuleId?: number,
) {
  const scope = ruleScopeKey(accountId);
  return rules.some((rule) => (
    rule.rule_id !== ignoreRuleId
    && ruleScopeKey(rule.account_id) === scope
    && rule.priority === priority
  ));
}

export function reorderPayloadForScope(rules: MailRule[], ruleId: number, direction: -1 | 1) {
  const movedRule = rules.find((rule) => rule.rule_id === ruleId);
  if (!movedRule) return [];

  const scoped = rulesInScope(rules, movedRule.account_id);
  const idx = scoped.findIndex((rule) => rule.rule_id === ruleId);
  const swapIdx = idx + direction;
  if (idx < 0 || swapIdx < 0 || swapIdx >= scoped.length) return [];

  const swapped = [...scoped];
  [swapped[idx], swapped[swapIdx]] = [swapped[swapIdx], swapped[idx]];
  return swapped.map((rule, index) => ({
    rule_id: rule.rule_id,
    priority: (index + 1) * 10,
  }));
}

export function rulePayloadWithAccountScope(rule: MailRuleInput, accountId: string | null) {
  return {
    ...rule,
    account_id: accountId,
  };
}
