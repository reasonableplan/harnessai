import { EventEmitter } from 'events';
import type { IMessageBus, IStateStore, Message, MessageHandler } from './types/index.js';
import { createLogger } from './logger.js';

const log = createLogger('MessageBus');

export class MessageBus implements IMessageBus {
  private emitter = new EventEmitter();
  private allHandlers: MessageHandler[] = [];
  private stateStore: IStateStore | null = null;

  constructor(stateStore?: IStateStore) {
    this.emitter.setMaxListeners(50);
    this.stateStore = stateStore ?? null;
  }

  /** StateStore를 나중에 설정 (bootstrap 순서상 MessageBus가 먼저 생성되는 경우) */
  setStateStore(stateStore: IStateStore): void {
    this.stateStore = stateStore;
  }

  async publish(message: Message): Promise<void> {
    // 메시지를 DB에 자동 저장 (감사 로그)
    if (this.stateStore) {
      try {
        await this.stateStore.saveMessage(message);
      } catch (error) {
        log.error({ err: error, messageType: message.type }, 'Failed to persist message');
      }
    }

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
