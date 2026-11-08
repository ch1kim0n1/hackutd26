import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Check, Info, Layers, Terminal } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { Drawer, DrawerContent, DrawerDescription, DrawerHeader, DrawerTitle, DrawerTrigger } from '@/components/ui/drawer'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { Progress } from '@/components/ui/progress'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { palette } from '@/styles/palette'
import { usePhantomStore } from '@/store/use-phantom-store'

export default function ComponentGallery() {
  const [level, setLevel] = useState([64])
  const [command, setCommand] = useState(false)
  const glow = usePhantomStore(state => state.glow)
  const setGlow = usePhantomStore(state => state.setGlow)
  const selectDevice = usePhantomStore(state => state.selectDevice)
  const selected = usePhantomStore(state => state.selectedDeviceId)
  const form = useForm<{ label: string }>({ defaultValues: { label: '' } })
  return <div className="space-y-6">
    <Alert><Info /><AlertTitle>Foundation preview</AlertTitle><AlertDescription>Editable shadcn source, Phantom tokens, and isolated component interactions. All examples use synthetic fixtures.</AlertDescription></Alert>
    <div className="token-grid">{Object.entries(palette).map(([name, color]) => <div key={name} className="token-swatch"><div style={{ background: color }} /><p>{name}</p><span>{color}</span></div>)}</div>
    <div className="gallery-grid">
      <Card><CardHeader><CardTitle>Actions & overlays</CardTitle><CardDescription>Keyboard accessible Radix primitives</CardDescription></CardHeader><CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2"><Button onClick={() => toast.success('Local notification example')}><Check />Show toast</Button><Button variant="outline" onClick={() => setCommand(true)}><Terminal />Command palette</Button></div>
        <div className="flex flex-wrap gap-2">
          <Dialog><DialogTrigger asChild><Button variant="secondary">Open dialog</Button></DialogTrigger><DialogContent><DialogHeader><DialogTitle>Dialog example</DialogTitle><DialogDescription>Accessible focus trapping and Escape dismissal. No operation is executed.</DialogDescription></DialogHeader><p className="text-sm">Use this primitive for future review workflows.</p></DialogContent></Dialog>
          <Sheet><SheetTrigger asChild><Button variant="outline">Open sheet</Button></SheetTrigger><SheetContent><SheetHeader><SheetTitle>Context sheet</SheetTitle><SheetDescription>A future detail surface for selected assets.</SheetDescription></SheetHeader></SheetContent></Sheet>
          <Drawer><DrawerTrigger asChild><Button variant="outline">Open drawer</Button></DrawerTrigger><DrawerContent><DrawerHeader><DrawerTitle>Drawer example</DrawerTitle><DrawerDescription>Responsive secondary content with touch interaction.</DrawerDescription></DrawerHeader><p className="p-6 text-center text-sm">Synthetic fixture content</p></DrawerContent></Drawer>
          <DropdownMenu><DropdownMenuTrigger asChild><Button variant="outline">Menu</Button></DropdownMenuTrigger><DropdownMenuContent><DropdownMenuItem onSelect={() => toast.info('Fixture copied')}>Copy fixture ID</DropdownMenuItem><DropdownMenuItem onSelect={() => toast.info('Example menu action')}>Inspect example</DropdownMenuItem></DropdownMenuContent></DropdownMenu>
        </div>
        <div className="flex items-center gap-2"><Badge>Default</Badge><Badge variant="secondary">Synthetic</Badge><Badge variant="outline">Pending</Badge><Tooltip><TooltipTrigger asChild><Button size="icon" variant="ghost" aria-label="Component help"><Info /></Button></TooltipTrigger><TooltipContent>Phantom component tooltip</TooltipContent></Tooltip></div>
      </CardContent></Card>
      <Card><CardHeader><CardTitle>Forms & shared state</CardTitle><CardDescription>Zustand links this selection to tables and 3D</CardDescription></CardHeader><CardContent className="space-y-4">
        <div className="space-y-2"><Label htmlFor="fixture-select">Selected fixture</Label><Select value={selected ?? 'none'} onValueChange={id => selectDevice(id === 'none' ? null : id)}><SelectTrigger id="fixture-select"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">None</SelectItem><SelectItem value="rack-01">Compute rack 01</SelectItem><SelectItem value="rover-01">Survey rover</SelectItem><SelectItem value="sensor-01">Cabinet sensor</SelectItem></SelectContent></Select></div>
        <div className="flex items-center justify-between"><Label htmlFor="gallery-glow">Enable 3D bloom</Label><Switch id="gallery-glow" checked={glow} onCheckedChange={setGlow} /></div>
        <Form {...form}><form className="space-y-3" onSubmit={form.handleSubmit(values => toast.success(`Fixture label: ${values.label}`))}><FormField control={form.control} name="label" rules={{ required: 'Enter a label', maxLength: { value: 60, message: 'Use 60 characters or fewer' } }} render={({ field }) => <FormItem><FormLabel>Example label</FormLabel><FormControl><Input placeholder="e.g. Lab A sensor" {...field} /></FormControl><FormMessage /></FormItem>} /><Button type="submit" variant="secondary">Validate form</Button></form></Form>
      </CardContent></Card>
      <Card><CardHeader><CardTitle>Progress & panels</CardTitle><CardDescription>Adjustable controls and resizable regions</CardDescription></CardHeader><CardContent className="space-y-5">
        <div className="flex justify-between text-sm"><Label htmlFor="example-level">Example level</Label><span>{level[0]}%</span></div><Slider id="example-level" aria-label="Example level" value={level} onValueChange={setLevel} max={100} step={1} /><Progress value={level[0]} aria-label="Example progress" />
        <ResizablePanelGroup orientation="horizontal" className="min-h-28 rounded-md border"><ResizablePanel defaultSize="55%" minSize="25%"><div className="flex h-full items-center justify-center p-4 text-sm">Primary panel</div></ResizablePanel><ResizableHandle withHandle /><ResizablePanel defaultSize="45%" minSize="25%"><div className="flex h-full items-center justify-center p-4 text-sm">Context</div></ResizablePanel></ResizablePanelGroup>
      </CardContent></Card>
      <Card><CardHeader><CardTitle>Tabs & records</CardTitle><CardDescription>Scrollable semantic data surfaces</CardDescription></CardHeader><CardContent>
        <Tabs defaultValue="records"><TabsList><TabsTrigger value="records">Records</TabsTrigger><TabsTrigger value="notes">Notes</TabsTrigger></TabsList><TabsContent value="records"><ScrollArea className="h-44"><Table><TableHeader><TableRow><TableHead>Fixture</TableHead><TableHead>State</TableHead></TableRow></TableHeader><TableBody>{['Rack 01', 'Rack 02', 'Rover', 'Sensor', 'Gateway'].map(name => <TableRow key={name}><TableCell>{name}</TableCell><TableCell><Badge variant="outline">Synthetic</Badge></TableCell></TableRow>)}</TableBody></Table></ScrollArea></TabsContent><TabsContent value="notes"><p className="note py-4">Source components live in src/components/ui. The app shell also demonstrates the responsive Sidebar component.</p></TabsContent></Tabs>
      </CardContent></Card>
    </div>
    <Dialog open={command} onOpenChange={setCommand}><DialogContent className="p-0"><DialogHeader className="sr-only"><DialogTitle>Fixture command palette</DialogTitle><DialogDescription>Search local fixture selection actions.</DialogDescription></DialogHeader><Command><CommandInput placeholder="Find a fixture…" /><CommandList><CommandEmpty>No fixture found.</CommandEmpty><CommandGroup heading="Select fixture">{['rack-01', 'rover-01', 'sensor-01'].map(id => <CommandItem key={id} onSelect={() => { selectDevice(id); setCommand(false) }}><Layers />{id}</CommandItem>)}</CommandGroup></CommandList></Command></DialogContent></Dialog>
  </div>
}
