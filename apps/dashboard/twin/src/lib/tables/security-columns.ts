import type { ColDef } from 'ag-grid-community'
import type { SecurityDevice } from '@/types/security'

export const securityColumns: ColDef<SecurityDevice>[] = [
  { field: 'name', headerName: 'Device', minWidth: 180, flex: 1.4 },
  { field: 'kind', minWidth: 130, flex: 1 },
  { field: 'status', minWidth: 130, flex: 1 },
  { field: 'zone', minWidth: 130, flex: 1 },
  { field: 'address', minWidth: 140, flex: 1 },
  { field: 'provenance', minWidth: 140, flex: 1 },
]
