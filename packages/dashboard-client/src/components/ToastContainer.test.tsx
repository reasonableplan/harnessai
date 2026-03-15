import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useOfficeStore } from '@/stores/office-store';
import ToastContainer from './ToastContainer';

beforeEach(() => {
  useOfficeStore.setState({ toasts: [] });
});

describe('ToastContainer', () => {
  it('토스트가 없으면 토스트 아이템 렌더링 없음', () => {
    render(<ToastContainer />);
    expect(screen.queryByText(/\[/)).toBeNull(); // 아이콘 없음
  });

  it('success 토스트 메시지 렌더링', () => {
    useOfficeStore.setState({
      toasts: [{ id: 't1', type: 'success', title: '완료', message: '태스크 성공' }],
    });
    render(<ToastContainer />);
    expect(screen.getByText('완료')).toBeInTheDocument();
    expect(screen.getByText('태스크 성공')).toBeInTheDocument();
  });

  it('success 토스트 아이콘 [+] 표시', () => {
    useOfficeStore.setState({
      toasts: [{ id: 't1', type: 'success', title: 'Done', message: '' }],
    });
    render(<ToastContainer />);
    expect(screen.getByText('[+]')).toBeInTheDocument();
  });

  it('error 토스트 아이콘 [!] 표시', () => {
    useOfficeStore.setState({
      toasts: [{ id: 't2', type: 'error', title: 'Error', message: 'fail' }],
    });
    render(<ToastContainer />);
    expect(screen.getByText('[!]')).toBeInTheDocument();
  });

  it('토스트 클릭 시 제거', async () => {
    const user = userEvent.setup();
    useOfficeStore.setState({
      toasts: [{ id: 't1', type: 'info', title: '알림', message: '내용' }],
    });
    render(<ToastContainer />);
    await user.click(screen.getByText('알림'));
    expect(useOfficeStore.getState().toasts).toHaveLength(0);
  });

  it('여러 토스트 동시 렌더링', () => {
    useOfficeStore.setState({
      toasts: [
        { id: 't1', type: 'success', title: '성공', message: '' },
        { id: 't2', type: 'error', title: '실패', message: '' },
      ],
    });
    render(<ToastContainer />);
    expect(screen.getByText('성공')).toBeInTheDocument();
    expect(screen.getByText('실패')).toBeInTheDocument();
  });
});
