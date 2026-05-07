# React Native + Expo — State Management Guidelines

## Zustand 단일화

Web (`react-vite`) 와 일관 — 서버 상태 라이브러리 (React Query / SWR / TanStack) **금지**.

## 도메인별 store 위치

```
src/
  shared/store/
    auth.store.ts          # 여러 화면 공유
  containers/
    items/
      store/items.store.ts # 화면 전용
    settings/
      store/settings.store.ts
```

## Store 구조 (도메인 1개 당)

```ts
// src/containers/items/store/items.store.ts
import { create } from "zustand";

interface ItemsState {
  items: Item[];
  loading: boolean;
  error: string | null;
  // actions
  fetchItems: () => Promise<void>;
  createItem: (input: CreateItemInput) => Promise<void>;
}

export const useItemsStore = create<ItemsState>((set) => ({
  items: [],
  loading: false,
  error: null,
  fetchItems: async () => {
    set({ loading: true, error: null });
    try {
      const res = await client.get<Item[]>("/items");
      set({ items: res.data });
    } catch (e) {
      set({ error: extractErrorMessage(e) });
    } finally {
      set({ loading: false });
    }
  },
  createItem: async (input) => { /* 낙관적 업데이트 */ },
}));
```

## 낙관적 업데이트 (모바일에서 중요)

네트워크 지연 → 사용자 즉시 피드백:

```ts
createItem: async (input) => {
  const tempId = nanoid();
  const optimistic = { ...input, id: tempId, _pending: true };
  set((s) => ({ items: [...s.items, optimistic] }));
  try {
    const res = await client.post("/items", input);
    set((s) => ({ items: s.items.map(i => i.id === tempId ? res.data : i) }));
  } catch (e) {
    set((s) => ({ items: s.items.filter(i => i.id !== tempId), error: extractErrorMessage(e) }));
  }
},
```

## 오프라인 큐 (optional, mobile.lifecycle 의 정책 따름)

스킬레톤 의 `mobile.lifecycle` 에 "오프라인 큐 동기화" 명시 시:

```ts
// src/shared/store/offline-queue.store.ts
interface QueuedAction {
  id: string;
  type: "create_item" | "update_profile" | ...;
  payload: unknown;
  retries: number;
}

export const useOfflineQueue = create<{
  queue: QueuedAction[];
  enqueue: (action: QueuedAction) => void;
  flush: () => Promise<void>;
}>(/* ... */);
```

flush 호출은 `NetInfo` 의 isConnected → true 이벤트에서.

## Persistence (AsyncStorage 또는 MMKV)

토큰 / 사용자 설정 같은 것만:
```ts
import { persist, createJSONStorage } from "zustand/middleware";
import AsyncStorage from "@react-native-async-storage/async-storage";

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({ /* ... */ }),
    { name: "auth-store", storage: createJSONStorage(() => AsyncStorage) },
  )
);
```

> **시크릿 (refresh token, JWT) 은 AsyncStorage 에 persist X** — `expo-secure-store` 별도 사용

## 금지 사항

- React Query / SWR / TanStack Query / RTK Query
- Redux / MobX
- Context API 로 도메인 store (auth 같은 단순 state 만 OK)
- 컴포넌트 안 axios 직접 호출 — store action 으로
- `set` 안에서 또 다른 `set` 호출 (race) — sync 또는 await 분리
