import { useState } from 'react'
import { AgGridReact } from 'ag-grid-react'
import { AllCommunityModule, ModuleRegistry, themeQuartz } from 'ag-grid-community'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { devices } from '@/mock/security'
import { securityColumns } from '@/lib/tables/security-columns'
import { palette } from '@/styles/palette'
import { usePhantomStore } from '@/store/use-phantom-store'

ModuleRegistry.registerModules([AllCommunityModule])
const theme = themeQuartz.withParams({
  backgroundColor: palette.background, foregroundColor: palette.text,
  headerBackgroundColor: palette.panel, borderColor: '#263b53',
  accentColor: palette.wall, fontFamily: 'ui-monospace, monospace', fontSize: 12,
})
export default function SecurityTableExample() {
  const [filter, setFilter] = useState('')
  const selected = usePhantomStore(state => state.selectedDeviceId)
  const select = usePhantomStore(state => state.selectDevice)
  return <div className="space-y-4">
    <div className="example-toolbar"><div className="space-y-2"><Label htmlFor="device-filter">Search fixture devices</Label><Input id="device-filter" className="w-72" placeholder="Name, zone, status…" value={filter} onChange={event => setFilter(event.target.value)} /></div><span className="note" role="status">Shared selection: {selected ?? 'none'}</span></div>
    <div className="h-[390px] w-full" data-testid="security-grid"><AgGridReact theme={theme} rowData={devices} columnDefs={securityColumns} defaultColDef={{ sortable: true, filter: true, resizable: true }} quickFilterText={filter} getRowId={params => params.data.id} onRowClicked={event => event.data && select(event.data.id)} /></div>
    <p className="note">AG Grid Community · sort headers, filter records, resize columns, or click a row to update Zustand. Addresses use the documentation-only 192.0.2.0/24 range.</p>
  </div>
}
