import { useEffect, useState } from 'react';
import { useNetworkStatus } from '@/hooks/use-network-status';
import { useSyncManager } from '@/hooks/use-sync-manager';

export function OfflineBanner(): React.ReactElement | null {
  const { isOnline, wasOffline, acknowledgeReconnection } = useNetworkStatus();
  const { isSyncing, queueLength, retrySync } = useSyncManager();
  const [dismissed, setDismissed] = useState(false);
  const [prevQueueLength, setPrevQueueLength] = useState(queueLength);

  // un-dismiss during render when the queue changes and items remain.
  if (queueLength !== prevQueueLength) {
    setPrevQueueLength(queueLength);
    if (queueLength > 0) {
      setDismissed(false);
    }
  }

  // show "back online" toast briefly
  useEffect(() => {
    if (wasOffline && isOnline) {
      const timer = setTimeout(() => {
        acknowledgeReconnection();
      }, 5000);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [wasOffline, isOnline, acknowledgeReconnection]);

  // syncing indicator
  if (isSyncing) {
    return (
      <div
        role="status"
        data-testid="sync-banner"
        className={
          'flex items-center gap-2 ' +
          'bg-blue-600 px-4 py-2 text-sm text-white'
        }
      >
        <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d={'M4 12a8 8 0 018-8V0C5.373 0 0 5.373 ' + '0 12h4z'}
          />
        </svg>
        <span>
          Syncing {queueLength} pending{' '}
          {queueLength === 1 ? 'change' : 'changes'}...
        </span>
      </div>
    );
  }

  // back online notification
  if (wasOffline && isOnline && queueLength === 0) {
    return (
      <div
        role="status"
        data-testid="reconnected-banner"
        className={
          'flex items-center justify-between ' +
          'bg-green-600 px-4 py-2 text-sm text-white'
        }
      >
        <span>Back online. All changes synced.</span>
        <button
          type="button"
          onClick={acknowledgeReconnection}
          className={'ml-4 rounded px-2 py-0.5 text-xs ' + 'hover:bg-green-700'}
          aria-label="Dismiss reconnected notification"
        >
          Dismiss
        </button>
      </div>
    );
  }

  // offline banner
  if (!isOnline && !dismissed) {
    return (
      <div
        role="alert"
        data-testid="offline-banner"
        className={
          'flex items-center justify-between ' +
          'bg-amber-600 px-4 py-2 text-sm text-white'
        }
      >
        <div className="flex items-center gap-2">
          <svg
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d={
                'M18.364 5.636a9 9 0 010 12.728M5.636 ' +
                '5.636a9 9 0 000 12.728'
              }
            />
            <line
              x1="2"
              y1="2"
              x2="22"
              y2="22"
              stroke="currentColor"
              strokeWidth="2"
            />
          </svg>
          <span>
            You are offline. Changes will be saved and synced when you
            reconnect.
            {queueLength > 0 && (
              <span className="ml-1 font-medium">
                {queueLength} {queueLength === 1 ? 'item' : 'items'} pending
                sync.
              </span>
            )}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className={'ml-4 rounded px-2 py-0.5 text-xs ' + 'hover:bg-amber-700'}
          aria-label="Dismiss offline notification"
        >
          Dismiss
        </button>
      </div>
    );
  }

  // show pending queue when online but items remain
  if (isOnline && queueLength > 0 && !dismissed) {
    return (
      <div
        role="status"
        data-testid="queue-banner"
        className={
          'flex items-center justify-between ' +
          'bg-amber-500 px-4 py-2 text-sm text-white'
        }
      >
        <span>
          {queueLength} {queueLength === 1 ? 'change' : 'changes'} failed to
          sync.
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={retrySync}
            className={'rounded px-2 py-0.5 text-xs ' + 'hover:bg-amber-600'}
          >
            Retry
          </button>
          <button
            type="button"
            onClick={() => setDismissed(true)}
            className={'rounded px-2 py-0.5 text-xs ' + 'hover:bg-amber-600'}
            aria-label="Dismiss queue notification"
          >
            Dismiss
          </button>
        </div>
      </div>
    );
  }

  return null;
}
