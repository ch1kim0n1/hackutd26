import spacetimedb from './schema';
import type { ChatKindValue } from './schema';
import {
  audit,
  boundedString,
  MAX_CHAT_BODY_CHARS,
  newId,
  requireIncidentAccess,
  tagValue,
} from './lib';
import { SenderError, t } from 'spacetimedb/server';

// postChatMessage — incident-scoped team chat (Winstead R05).
// Responder-level access required (observers are read-only).
// clientNonce is globally unique: retries are idempotent, collisions rejected.
export const postChatMessage = spacetimedb.reducer(
  {
    incidentId: t.string(),
    body: t.string(),
    clientNonce: t.string(),
  },
  (ctx, args) => {
    const incidentId = boundedString(args.incidentId, 128, 'incident_id');
    requireIncidentAccess(ctx, incidentId, 'responder');
    if (ctx.db.incidents.id.find(incidentId) === null) throw new SenderError('unknown incident');

    const body = boundedString(args.body, MAX_CHAT_BODY_CHARS, 'body');
    const nonce = boundedString(args.clientNonce, 128, 'client_nonce');

    const dup = ctx.db.chatMessages.clientNonce.find(nonce);
    if (dup !== null) {
      if (dup.sender.isEqual(ctx.sender) && dup.incidentId === incidentId) {
        return; // exact retry: idempotent no-op
      }
      throw new SenderError('client_nonce already used');
    }

    const p = ctx.db.usersAndRoles.userId.find(ctx.sender);
    ctx.db.chatMessages.insert({
      id: 0n,
      incidentId,
      sender: ctx.sender,
      senderRole: p?.role.tag ?? 'unknown',
      kind: tagValue<ChatKindValue>('user'),
      body,
      refId: '',
      createdAt: ctx.timestamp,
      clientNonce: nonce,
      traceId: newId('tr', ctx),
    });
    audit(ctx, {
      actor: ctx.sender,
      operation: 'chat.post',
      entity: `chat:${incidentId}`,
      incidentId,
      after: { clientNonce: nonce, bodyPreview: body.slice(0, 120) },
      traceId: nonce,
    });
  }
);
