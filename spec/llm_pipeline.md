# LLM Context Assembly & Conversation

## 1. Context Assembly Algorithm

```typescript
async function assembleContext(
  conversationId: UUID,
  userId: UUID,
  userMessage: string
): Promise<LLMContext> {
  // 1. Load conversation
  const conversation = await loadConversation(conversationId);

  // 2. Build system message
  const systemMessage = buildSystemMessage(conversation);
  const systemTokens = countTokens(systemMessage);

  // 3. Load history
  const historyMessages = await loadHistory(conversationId, userId);
  const historyTokens = countTokens(historyMessages);

  // 4. Perform retrieval
  const contentResults = await retrieve({
    query: userMessage,
    scope: { type: 'global' },
    spaces: ['content'],
    k: 8,
    user_id: userId
  });

  const thoughtResults = await retrieve({
    query: userMessage,
    scope: { type: 'global' },
    spaces: ['thoughts'],
    k: 5,
    user_id: userId
  });

  const metadataResults = await retrieve({
    query: userMessage,
    scope: { type: 'global' },
    spaces: ['metadata'],
    k: 3,
    user_id: userId
  });

  const retrievalTokens =
    countTokens(contentResults) +
    countTokens(thoughtResults) +
    countTokens(metadataResults);

  const userMessageTokens = countTokens(userMessage);

  // 5. Check budget
  const totalTokens =
    systemTokens +
    historyTokens +
    retrievalTokens +
    userMessageTokens;

  const BUDGET = 32000;
  const RESERVE = 7500;  // for completion

  if (totalTokens > BUDGET - RESERVE) {
    // Apply shrinking strategy
    return shrinkContext({
      systemMessage,
      systemTokens,
      history: historyMessages,
      historyTokens,
      contentResults,
      thoughtResults,
      metadataResults,
      retrievalTokens,
      userMessage,
      userMessageTokens,
      budget: BUDGET - RESERVE
    });
  }

  return {
    systemMessage,
    history: historyMessages,
    retrievalContent: contentResults.results,
    retrievalThoughts: thoughtResults.results,
    retrievalMetadata: metadataResults.results,
    totalTokens
  };
}
```

## 2. System Message

```typescript
function buildSystemMessage(conversation: Conversation): string {
  let message = `You are a helpful assistant with access to the user's personal knowledge base of documents, podcasts, videos, annotations, and conversations.

When answering questions, cite specific sources by title and location (page number, timestamp, or section).

`;

  if (conversation.summary_state) {
    message += `## Conversation Summary\n\n${conversation.summary_state}\n\n`;
  }

  message += `Provide thoughtful, accurate answers based on the available context.`;

  return message;
}
```

## 3. History Selection

Load most recent 20 messages, filter by visibility, include stubs for private messages:

```typescript
async function loadHistory(
  conversationId: UUID,
  userId: UUID
): Promise<Message[]> {
  const rawMessages = await db.query(`
    SELECT * FROM messages
    WHERE conversation_id = $1
    ORDER BY created_at DESC
    LIMIT 20
  `, [conversationId]);

  rawMessages.reverse();  // chronological order

  const visibleMessages = [];
  for (const msg of rawMessages) {
    if (await isVisible(userId, msg)) {
      visibleMessages.push(msg);
    } else {
      // Include stub for private messages
      visibleMessages.push({
        id: msg.id,
        role: msg.role,
        content: '[Private message]',
        created_at: msg.created_at,
        is_stub: true
      });
    }
  }

  return visibleMessages;
}
```

## 4. Token Budget Shrinking

When total tokens exceed budget, shrink using priority:

**Priority**: system > user message > history > content > thoughts > metadata

```typescript
function shrinkContext(input: ContextShrinkInput): LLMContext {
  let availableForContext = budget - systemTokens - userMessageTokens;

  if (availableForContext <= 0) {
    throw new Error('User message too long');
  }

  // Allocate budgets
  let historyBudget = Math.min(8000, availableForContext * 0.4);
  let contentBudget = Math.min(8000, availableForContext * 0.4);
  let thoughtBudget = Math.min(4000, availableForContext * 0.15);
  let metadataBudget = Math.min(500, availableForContext * 0.05);

  // Scale if still over budget
  const totalAllocated = historyBudget + contentBudget + thoughtBudget + metadataBudget;
  if (totalAllocated > availableForContext) {
    const scale = availableForContext / totalAllocated;
    historyBudget *= scale;
    contentBudget *= scale;
    thoughtBudget *= scale;
    metadataBudget *= scale;
  }

  // Truncate each section
  const truncatedHistory = truncateMessages(history, historyBudget);
  const truncatedContent = truncateResults(contentResults.results, contentBudget);
  const truncatedThoughts = truncateResults(thoughtResults.results, thoughtBudget);
  const truncatedMetadata = truncateResults(metadataResults.results, metadataBudget);

  return {
    systemMessage,
    history: truncatedHistory,
    retrievalContent: truncatedContent,
    retrievalThoughts: truncatedThoughts,
    retrievalMetadata: truncatedMetadata,
    totalTokens: // recompute
  };
}
```

## 5. Prompt Structure

```
{system_message}

## Conversation History

{history}

## Retrieved Content

{content_chunks}

## Your Notes and Thoughts

{thought_chunks}

## Available Documents

{metadata}

## Current Question

**user**: {user_message}

**assistant**:
```

Format retrieval results with source attribution:

```
[{title}, {section_title}, {timestamp/page}]
{chunk_text}
```

## 6. Model Selection

**Supported models** (as of 2024-11-25):

- `gpt-4-turbo` (OpenAI)
- `gpt-4o` (OpenAI)
- `claude-3-5-sonnet-20241022` (Anthropic)
- `claude-3-opus-20240229` (Anthropic)
- `gemini-1.5-pro` (Google)

**Selection**: User chooses via UI dropdown, default `gpt-4-turbo`

**Context assembly**: Identical across all models; provider-specific formatting applied at call time

**No replay guarantee**: System does NOT guarantee bitwise-identical outputs when re-generating same message

## 7. Conversation Summary Job (Phase 2+)

When conversation ≥ 30 messages or ≥ 10 new messages:

1. Load message history
2. Build summarization prompt
3. Call LLM to summarize
4. Update `conversation.summary_state`
5. Enqueue embedding job for summary

