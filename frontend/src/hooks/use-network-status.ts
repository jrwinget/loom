import { useCallback, useEffect, useState } from 'react';

interface NetworkStatus {
  isOnline: boolean;
  wasOffline: boolean;
  acknowledgeReconnection: () => void;
}

export function useNetworkStatus(): NetworkStatus {
  const [isOnline, setIsOnline] = useState(
    typeof navigator !== 'undefined' ? navigator.onLine : true,
  );
  const [wasOffline, setWasOffline] = useState(false);

  useEffect(() => {
    const handleOnline = (): void => {
      setIsOnline(true);
      setWasOffline(true);
    };

    const handleOffline = (): void => {
      setIsOnline(false);
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  const acknowledgeReconnection = useCallback(() => {
    setWasOffline(false);
  }, []);

  return { isOnline, wasOffline, acknowledgeReconnection };
}
