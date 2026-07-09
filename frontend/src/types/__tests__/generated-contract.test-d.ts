/**
 * compile-time contract guards: the hand-written camelCase types the
 * app consumes must stay assignable from the generated wire shapes
 * (camelized the way the api client camelizes at runtime). a backend
 * field rename, casing change, or envelope reshape now fails
 * `pnpm typecheck` instead of shipping as a runtime undefined — the
 * exact drift class behind the v0.1.13 crashes.
 *
 * vitest runs .test-d.ts files through tsc only (no runtime).
 */

import { expectTypeOf } from 'vitest';
import type { Camel, Schemas } from '@/types/generated';
import type { Case, User } from '@/types';
import type { Asset } from '@/types/asset';
import type { ExportBundle } from '@/types/export';
import type { Capabilities } from '@/hooks/use-capabilities';

type WireCase = Camel<Schemas['CaseResponse']>;
type WireUser = Camel<Schemas['UserResponse']>;
type WireAsset = Camel<Schemas['AssetResponse']>;
type WireExport = Camel<Schemas['ExportResponse']>;
type WireExportList = Camel<Schemas['ExportListResponse']>;
type WireWorkflowStatus = Camel<Schemas['WorkflowStatusResponse']>;
type WireCapabilities = Camel<Schemas['CapabilitiesResponse']>;

// the wire shape must satisfy the hand-written type: every field the
// app reads exists on the wire with a compatible type. (the reverse
// direction is intentionally not asserted — the app may consume a
// subset of what the backend sends. where the app narrows a wire
// string into a literal union, assert the field exists instead.)
expectTypeOf<WireCase>().toMatchTypeOf<Case>();
expectTypeOf<WireUser>().toMatchTypeOf<User>();
expectTypeOf<WireExportList['total']>().toEqualTypeOf<number>();
expectTypeOf<WireExportList['items'][number]['storageKey']>().toMatchTypeOf<
  ExportBundle['storageKey']
>();

// wider hand-written unions (e.g. status: string vs enum) are fine;
// spot-check load-bearing fields precisely
expectTypeOf<WireAsset['processingStatus']>().toMatchTypeOf<
  Asset['processingStatus'] | string
>();
expectTypeOf<WireAsset['sha256Hash']>().toEqualTypeOf<string>();
expectTypeOf<WireAsset['processingError']>().toMatchTypeOf<
  string | null | undefined
>();

expectTypeOf<WireExport['downloadUrl']>().toMatchTypeOf<
  ExportBundle['downloadUrl'] | undefined
>();

expectTypeOf<WireWorkflowStatus['workflowId']>().toEqualTypeOf<string>();
expectTypeOf<WireWorkflowStatus['errorCode']>().toMatchTypeOf<
  string | null | undefined
>();
expectTypeOf<WireWorkflowStatus['stepsTotal']>().toMatchTypeOf<
  number | null | undefined
>();

expectTypeOf<WireCapabilities['profile']>().toMatchTypeOf<
  Capabilities['profile']
>();
