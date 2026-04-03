import { useState } from 'react';
import { useMfaSetup, useMfaVerify } from '@/hooks/use-mfa';

export function MfaSetup() {
  const [code, setCode] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState<
    string[] | null
  >(null);

  const setup = useMfaSetup();
  const verify = useMfaVerify();

  const provisioningUri = setup.data?.provisioning_uri;

  const handleSetup = () => {
    setup.mutate(undefined);
  };

  const handleVerify = () => {
    verify.mutate(
      { code },
      {
        onSuccess: (data) => {
          setRecoveryCodes(data.recovery_codes);
          setCode('');
        },
      },
    );
  };

  if (recoveryCodes) {
    return (
      <div className="mfa-setup">
        <h3>MFA Enabled</h3>
        <p>
          Save these recovery codes in a safe place. Each
          code can only be used once.
        </p>
        <ul className="recovery-codes">
          {recoveryCodes.map((c) => (
            <li key={c}>
              <code>{c}</code>
            </li>
          ))}
        </ul>
        <p>
          <strong>
            These codes will not be shown again.
          </strong>
        </p>
      </div>
    );
  }

  return (
    <div className="mfa-setup">
      <h3>Set Up Two-Factor Authentication</h3>

      {!provisioningUri ? (
        <button
          onClick={handleSetup}
          disabled={setup.isPending}
          type="button"
        >
          {setup.isPending
            ? 'Generating...'
            : 'Generate QR Code'}
        </button>
      ) : (
        <div>
          <p>
            Scan this QR code with your authenticator app:
          </p>
          <img
            src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(provisioningUri)}`}
            alt="TOTP QR Code"
            width={200}
            height={200}
          />
          <p>
            Or enter this key manually:{' '}
            <code>
              {new URL(provisioningUri).searchParams.get(
                'secret',
              )}
            </code>
          </p>

          <div>
            <label htmlFor="totp-code">
              Enter the 6-digit code from your app:
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
            <button
              onClick={handleVerify}
              disabled={
                verify.isPending || code.length !== 6
              }
              type="button"
            >
              {verify.isPending
                ? 'Verifying...'
                : 'Verify & Enable'}
            </button>
          </div>

          {verify.isError && (
            <p className="error">
              Invalid code. Please try again.
            </p>
          )}
        </div>
      )}

      {setup.isError && (
        <p className="error">
          Failed to set up MFA. Please try again.
        </p>
      )}
    </div>
  );
}
