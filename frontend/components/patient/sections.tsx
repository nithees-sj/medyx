"use client";

import { Upload } from "lucide-react";
import Link from "next/link";

import { useProfileId } from "@/components/patient/profile-shell";
import { ReviewView } from "@/components/patient/review-view";
import { UploadView } from "@/components/patient/upload-view";
import { DocumentsView } from "@/components/record/documents-view";
import { MedicationsView } from "@/components/record/medications-view";
import { TimelineView } from "@/components/record/timeline-view";
import { TrendsView } from "@/components/record/trends-view";
import { buttonVariants } from "@/components/ui/button";

function UploadCta({ id }: { id: string }) {
  return (
    <Link href={`/app/p/${id}/upload`} className={buttonVariants()}>
      <Upload /> Upload documents
    </Link>
  );
}

export function UploadSection() {
  const id = useProfileId();
  return <UploadView profileId={id} base={`/app/p/${id}`} />;
}

export function ReviewSection() {
  return <ReviewView profileId={useProfileId()} />;
}

export function TimelineSection() {
  const id = useProfileId();
  return <TimelineView profileId={id} emptyAction={<UploadCta id={id} />} />;
}

export function TrendsSection() {
  const id = useProfileId();
  return <TrendsView profileId={id} emptyAction={<UploadCta id={id} />} />;
}

export function MedicationsSection() {
  const id = useProfileId();
  return <MedicationsView profileId={id} canStop emptyAction={<UploadCta id={id} />} />;
}

export function DocumentsSection() {
  const id = useProfileId();
  return <DocumentsView profileId={id} reviewHref={`/app/p/${id}/review`} canRetry emptyAction={<UploadCta id={id} />} />;
}
