import { useState } from 'react';
import { getApiOrigin } from '@/lib/api-client';
import { useAuthStore } from '@/stores/auth-store';

interface MfaSetupData {
  provisioning_uri: string;
  qr_code_base64: string;
}

export function MfaSetup() {
  const token = useAuthStore((s) => s.token);
  const [data, setData] = useState<MfaSetupData | null>(null);
  const [code, setCode] = useState('');
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSetup() {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${getApiOrigin()}/mfa/setup`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
      });
      if (!res.ok) {
        const body = (await res.json()) as { detail?: string };
        throw new Error(body.detail ?? res.statusText);
      }
      setData((await res.json()) as MfaSetupData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'setup failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleVerify() {
    setError('');
    try {
      const res = await fetch(`${getApiOrigin()}/mfa/verify`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ code }),
      });
      if (!res.ok) {
        const body = (await res.json()) as { detail?: string };
        throw new Error(body.detail ?? res.statusText);
      }
      const result = (await res.json()) as { success: boolean };
      if (result.success) {
        setVerified(true);
      } else {
        setError('invalid code, try again');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'verification failed');
    }
  }

  if (verified) {
    return <p>MFA enabled successfully.</p>;
  }

  if (!data) {
    return (
      <div>
        <button onClick={handleSetup} disabled={loading}>
          {loading ? 'Setting up...' : 'Enable MFA'}
        </button>
        {error && <p role="alert">{error}</p>}
      </div>
    );
  }

  return (
    <div>
      <p>Scan this QR code with your authenticator app:</p>
      <img
        src={`data:image/png;base64,${data.qr_code_base64}`}
        alt="TOTP QR code"
        width={200}
        height={200}
      />
      <div>
        <label htmlFor="mfa-code">Verification code:</label>
        <input
          id="mfa-code"
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={6}
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
        <button onClick={handleVerify} disabled={code.length < 6}>
          Verify
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
