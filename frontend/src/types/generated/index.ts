import type { CamelCasedPropertiesDeep } from 'type-fest';
import type { components, paths } from './api';

// wire-truth schemas straight from the backend's openapi document.
// keys are snake_case exactly as serialized.
export type Schemas = components['schemas'];
export type Paths = paths;

// the api client camelizes response keys at runtime (see
// api-client.ts camelizeKeys); this mirrors that transform at the
// type level so hand-written camelCase types can be checked against
// the generated wire shapes.
//
// known divergence: OPAQUE_VALUE_KEYS (manifestData, detail, config,
// metadata, reasoning) are NOT recursively camelized at runtime.
// those fields are free-form json typed as unknown/Record in the
// schema, so the deep mapper does not misrepresent their contents.
export type Camel<T> = CamelCasedPropertiesDeep<T>;
