import { useState } from 'react';
import { useMfaChallenge } from '@/hooks/use-mfa';
import { useAuthStore } from '@/stores/auth-store';

interface MfaChallengeProps {
  challengeToken: string;
  onSuccess: () => void;
}

export function MfaChallenge({
  challengeToken,
  onSuccess,
}: MfaChallengeProps) {
  const [code, setCode] = useState('');
  const [useRecovery, setUseRecovery] = useState(false);
  const challenge = useMfaChallenge();
  const setAuth = useAuthStore((s) => s.setAuth);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    challenge.mutate(
      {
        challenge_token: challengeToken,
        code,
      },
      {
        onSuccess: (data) => {
          setAuth(data.access_token, {
            id: '',
            email: '',
            displayName: '',
            role: '',
          });
          onSuccess();
        },
      },
    );
  };

  return (
    <form onSubmit={handleSubmit} className="mfa-challenge">
      <h3>Two-Factor Authentication</h3>

      {useRecovery ? (
        <div>
          <label htmlFor="recovery-code">
            Enter a recovery code:
          </label>
          <input
            id="recovery-code"
            type="text"
            maxLength={12}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            autoComplete="off"
          />
        </div>
      ) : (
        <div>
          <label htmlFor="totp-code">
            Enter the 6-digit code from your
            authenticator:
          </label>
          <input
            id="totp-code"
            type="text"
            inputMode="numeric"
            pattern="[0-9]{6}"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            autoComplete="one-time-code"
          />
        </div>
      )}

      <button
        type="submit"
        disabled={challenge.isPending || code.length < 6}
      >
        {challenge.isPending ? 'Verifying...' : 'Verify'}
      </button>

      {challenge.isError && (
        <p className="error">
          Invalid code. Please try again.
        </p>
      )}

      <button
        type="button"
        className="link-button"
        onClick={() => {
          setUseRecovery(!useRecovery);
          setCode('');
        }}
      >
        {useRecovery
          ? 'Use authenticator app'
          : 'Use a recovery code'}
      </button>
    </form>
  );
}
