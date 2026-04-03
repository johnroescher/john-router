import { test, expect } from '@playwright/test';

test('suggested prompt produces a response', async ({ page }) => {
  await page.goto('/');

  const prompt = page.getByTestId('suggested-prompt').first();
  await expect(prompt).toBeVisible();

  const promptText = (await prompt.innerText()).trim();
  await prompt.click();

  const lastUserMessage = page.getByTestId('chat-message-user').last();
  await expect(lastUserMessage).toContainText(promptText, { timeout: 15_000 });

  const assistantMessage = page.getByTestId('chat-message-assistant').last();
  await expect(assistantMessage).toBeVisible({ timeout: 120_000 });

  const assistantText = (await assistantMessage.innerText()).trim();
  expect(assistantText.length).toBeGreaterThan(0);
});
