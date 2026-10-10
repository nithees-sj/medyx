"use client";

import { formatDistanceToNowStrict } from "date-fns";
import { ArrowLeft, MessageSquare, Pill, ShieldOff, Upload } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { ChatPanel } from "@/components/copilot/chat-panel";
import { DoctorAlertsTab } from "@/components/doctor/alerts-tab";
import { NotesTab } from "@/components/doctor/notes-tab";
import { PrescribeDrawer } from "@/components/doctor/prescribe-drawer";
import { SummaryTab } from "@/components/doctor/summary-tab";
import { UploadView } from "@/components/patient/upload-view";
import { DocumentsView } from "@/components/record/documents-view";
import { MedicationsView } from "@/components/record/medications-view";
import { TimelineView } from "@/components/record/timeline-view";
import { TrendsView } from "@/components/record/trends-view";
import { DocumentViewerProvider } from "@/components/record/viewer-context";
import { EmptyState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";
import { useMe } from "@/lib/hooks/auth";
import { SCOPE_LABEL, type Scope } from "@/lib/hooks/consents";
import { useWorkspaceProfile } from "@/lib/hooks/doctor";

export function Workspace() {
  const { id } = useParams<{ id: string }>();
  const { data: me } = useMe();
  const profile = useWorkspaceProfile(id);
  const [prescribing, setPrescribing] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [uploading, setUploading] = useState(false);

  if (profile.isLoading) return <LoadingState rows={4} />;
  if (profile.isError) {
    const status = profile.error instanceof ApiError ? profile.error.status : 0;
    return (
      <EmptyState
        icon={ShieldOff}
        title={status === 403 ? "You no longer have access to this record" : "This record couldn't be opened"}
        description={status === 403 ? "The patient's share has ended or was revoked. Ask them to share again." : profile.error.message}
        action={
          <Link href="/doctor" className={buttonVariants({ variant: "outline" })}>
            Back to patients
          </Link>
        }
      />
    );
  }
  const p = profile.data!;
  const access = p.access!;
  const has = (s: string) => access.scopes.includes(s);

  return (
    <DocumentViewerProvider>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0 space-y-4">
          <Link href="/doctor" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-4" /> Patients
          </Link>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">{p.display_name}</h1>
              <p className="text-sm text-muted-foreground">
                {p.age} yrs · {p.sex} · blood group {p.blood_group} · <span className="font-mono">{p.healththread_id}</span>
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {access.scopes.map((s) => (
                  <Badge key={s} variant="secondary">
                    {SCOPE_LABEL[s as Scope] ?? s}
                  </Badge>
                ))}
                <Badge variant="outline">{access.can_write ? "Can add & prescribe" : "Read-only"}</Badge>
                {access.expires_at && (
                  <span className="text-xs text-muted-foreground">Access ends in {formatDistanceToNowStrict(new Date(access.expires_at))}</span>
                )}
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" className="xl:hidden" onClick={() => setChatOpen(true)}>
                <MessageSquare /> Ask the record
              </Button>
              {access.can_write && has("medications") && (
                <Button onClick={() => setPrescribing(true)}>
                  <Pill /> Prescribe
                </Button>
              )}
            </div>
          </div>

          <Tabs defaultValue="summary">
            <TabsList variant="line" className="w-full justify-start overflow-x-auto">
              <TabsTrigger value="summary">Summary</TabsTrigger>
              <TabsTrigger value="timeline">Timeline</TabsTrigger>
              {has("labs") && <TabsTrigger value="trends">Trends</TabsTrigger>}
              <TabsTrigger value="alerts">
                Alerts
                {p.active_alerts > 0 && (
                  <span className={`ml-1 rounded-full px-1.5 text-[10px] font-semibold text-white ${p.critical_alerts ? "bg-critical" : "bg-warning"}`}>
                    {p.active_alerts}
                  </span>
                )}
              </TabsTrigger>
              {has("medications") && <TabsTrigger value="medications">Medicines</TabsTrigger>}
              <TabsTrigger value="documents">Documents</TabsTrigger>
              <TabsTrigger value="notes">Notes</TabsTrigger>
            </TabsList>
            <div className="pt-4">
              <TabsContent value="summary">
                <SummaryTab profileId={id} defaultSpecialty={me?.doctor?.specialty ?? "General Medicine"} />
              </TabsContent>
              <TabsContent value="timeline">
                <TimelineView profileId={id} />
              </TabsContent>
              <TabsContent value="trends">
                <TrendsView profileId={id} />
              </TabsContent>
              <TabsContent value="alerts">
                <DoctorAlertsTab profileId={id} />
              </TabsContent>
              <TabsContent value="medications">
                <MedicationsView profileId={id} />
              </TabsContent>
              <TabsContent value="documents">
                <div className="space-y-3">
                  {access.can_write && (
                    <Button size="sm" variant="outline" onClick={() => setUploading(true)}>
                      <Upload /> Add documents
                    </Button>
                  )}
                  <DocumentsView profileId={id} />
                </div>
              </TabsContent>
              <TabsContent value="notes">
                <NotesTab profileId={id} canWrite={access.can_write} />
              </TabsContent>
            </div>
          </Tabs>
        </div>

        <aside className="hidden xl:block">
          <div className="sticky top-20 h-[calc(100dvh-7rem)] overflow-hidden rounded-xl border bg-card">
            <ChatPanel profileId={id} canWrite={access.can_write} patientName={p.display_name} />
          </div>
        </aside>
      </div>

      <Sheet open={chatOpen} onOpenChange={setChatOpen}>
        <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-md">
          <SheetHeader className="sr-only">
            <SheetTitle>Ask the record</SheetTitle>
          </SheetHeader>
          <ChatPanel profileId={id} canWrite={access.can_write} patientName={p.display_name} />
        </SheetContent>
      </Sheet>
      <PrescribeDrawer profileId={id} open={prescribing} onOpenChange={setPrescribing} />
      <Dialog open={uploading} onOpenChange={setUploading}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Add documents to {p.display_name.split(" ")[0]}&apos;s record</DialogTitle>
          </DialogHeader>
          <UploadView profileId={id} />
        </DialogContent>
      </Dialog>
    </DocumentViewerProvider>
  );
}
