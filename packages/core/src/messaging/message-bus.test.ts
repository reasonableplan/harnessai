import { describe, it, expect, vi } from 'vitest';
import { MessageBus } from './message-bus.js';
import type { Message } from '../types/index.js';

function createMessage(type: string, payload: unknown = {}): Message {
  return {
    id: crypto.randomUUID(),
    type,
    from: 'test-agent',
    to: null,
    payload,
    traceId: crypto.randomUUID(),
    timestamp: new Date(),
  };
}

describe('MessageBus', () => {
  it('subscribe로 등록한 handler에 메시지가 전달된다', async () => {
    const bus = new MessageBus();
    const handler = vi.fn();

    bus.subscribe('board.move', handler);
    await bus.publish(createMessage('board.move', { column: 'Ready' }));

    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler.mock.calls[0][0].payload).toEqual({ column: 'Ready' });
  });

  it('다른 타입의 메시지는 전달되지 않는다', async () => {
    const bus = new MessageBus();
    const handler = vi.fn();

    bus.subscribe('board.move', handler);
    await bus.publish(createMessage('agent.status'));

    expect(handler).not.toHaveBeenCalled();
  });

  it('subscribeAll은 모든 메시지를 수신한다', async () => {
    const bus = new MessageBus();
    const handler = vi.fn();

    bus.subscribeAll(handler);
    await bus.publish(createMessage('board.move'));
    await bus.publish(createMessage('agent.status'));

    expect(handler).toHaveBeenCalledTimes(2);
  });

  it('unsubscribe로 구독 해제할 수 있다', async () => {
    const bus = new MessageBus();
    const handler = vi.fn();

    bus.subscribe('board.move', handler);
    bus.unsubscribe('board.move', handler);
    await bus.publish(createMessage('board.move'));

    expect(handler).not.toHaveBeenCalled();
  });

  it('unsubscribeAll로 전체 구독을 해제할 수 있다', async () => {
    const bus = new MessageBus();
    const handler = vi.fn();

    bus.subscribeAll(handler);
    bus.unsubscribeAll(handler);
    await bus.publish(createMessage('board.move'));

    expect(handler).not.toHaveBeenCalled();
  });

  it('handler 에러가 다른 handler에 영향을 주지 않는다', async () => {
    const bus = new MessageBus();
    const errorHandler = vi.fn(() => {
      throw new Error('handler error');
    });
    const normalHandler = vi.fn();

    bus.subscribe('board.move', errorHandler);
    bus.subscribe('board.move', normalHandler);

    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    await bus.publish(createMessage('board.move'));
    consoleSpy.mockRestore();

    expect(errorHandler).toHaveBeenCalledTimes(1);
    expect(normalHandler).toHaveBeenCalledTimes(1);
  });

  it('async handler의 에러도 격리된다', async () => {
    const bus = new MessageBus();
    const asyncErrorHandler = vi.fn(async () => {
      throw new Error('async error');
    });
    const normalHandler = vi.fn();

    bus.subscribeAll(asyncErrorHandler);
    bus.subscribeAll(normalHandler);

    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    await bus.publish(createMessage('board.move'));
    consoleSpy.mockRestore();

    expect(asyncErrorHandler).toHaveBeenCalledTimes(1);
    expect(normalHandler).toHaveBeenCalledTimes(1);
  });

  it('여러 타입에 각각 구독할 수 있다', async () => {
    const bus = new MessageBus();
    const moveHandler = vi.fn();
    const statusHandler = vi.fn();

    bus.subscribe('board.move', moveHandler);
    bus.subscribe('agent.status', statusHandler);

    await bus.publish(createMessage('board.move'));
    await bus.publish(createMessage('agent.status'));

    expect(moveHandler).toHaveBeenCalledTimes(1);
    expect(statusHandler).toHaveBeenCalledTimes(1);
  });

  it('stateStore가 주입되면 publish 시 메시지를 DB에 저장한다', async () => {
    const mockStateStore = { saveMessage: vi.fn().mockResolvedValue(undefined) };
    const bus = new MessageBus(mockStateStore as any);
    const msg = createMessage('board.move');

    await bus.publish(msg);

    expect(mockStateStore.saveMessage).toHaveBeenCalledTimes(1);
    expect(mockStateStore.saveMessage).toHaveBeenCalledWith(msg);
  });

  it('stateStore 없이 생성해도 publish가 정상 동작한다', async () => {
    const bus = new MessageBus();
    const handler = vi.fn();
    bus.subscribe('test', handler);

    await bus.publish(createMessage('test'));

    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('setStateStore로 나중에 stateStore를 주입할 수 있다', async () => {
    const bus = new MessageBus();
    const mockStateStore = { saveMessage: vi.fn().mockResolvedValue(undefined) };

    bus.setStateStore(mockStateStore as any);
    await bus.publish(createMessage('board.move'));

    expect(mockStateStore.saveMessage).toHaveBeenCalledTimes(1);
  });

  it('stateStore.saveMessage 실패해도 handler는 정상 실행된다', async () => {
    const mockStateStore = { saveMessage: vi.fn().mockRejectedValue(new Error('DB error')) };
    const bus = new MessageBus(mockStateStore as any);
    const handler = vi.fn();
    bus.subscribe('test', handler);

    await bus.publish(createMessage('test'));

    expect(handler).toHaveBeenCalledTimes(1);
  });
});
