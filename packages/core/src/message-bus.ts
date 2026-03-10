import { EventEmitter } from 'events';
import type { IMessageBus, Message, MessageHandler } from './types/index.js';
import { createLogger } from './logger.js';

const log = createLogger('MessageBus');

export class MessageBus implements IMessageBus {
  private emitter = new EventEmitter();
  private allHandlers: MessageHandler[] = [];

  constructor() {
    this.emitter.setMaxListeners(50);
  }

  async publish(message: Message): Promise<void> {
    // 타입별 구독자에게 전달 (async handler를 수집하여 await)
    const typeHandlers = this.emitter.listeners(message.type) as MessageHandler[];
    for (const handler of typeHandlers) {
      try {
        await handler(message);
      } catch (error) {
        log.error({ err: error, messageType: message.type }, 'Handler error');
      }
    }

    // 전체 구독자에게 전달 (대시보드용)
    for (const handler of this.allHandlers) {
      try {
        await handler(message);
      } catch (error) {
        log.error({ err: error }, 'allHandler error');
      }
    }
  }

  subscribe(type: string, handler: MessageHandler): void {
    this.emitter.on(type, handler);
  }

  subscribeAll(handler: MessageHandler): void {
    this.allHandlers.push(handler);
  }

  unsubscribe(type: string, handler: MessageHandler): void {
    this.emitter.off(type, handler);
  }

  unsubscribeAll(handler: MessageHandler): void {
    this.allHandlers = this.allHandlers.filter((h) => h !== handler);
  }
}
