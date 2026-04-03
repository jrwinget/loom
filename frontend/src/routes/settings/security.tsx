import { MfaSetup } from '@/components/auth/MfaSetup';

export function SecuritySettingsPage(): React.ReactElement {
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold">Security</h1>
        <p className="text-muted-foreground">
          Manage two-factor authentication
        </p>
      </div>

      <div className="rounded-lg border p-6">
        <MfaSetup />
      </div>
    </div>
  );
}
