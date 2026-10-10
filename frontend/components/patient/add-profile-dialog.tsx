"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, UserPlus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import {
  emptyProfile,
  fieldErrors,
  ProfileFields,
  type ProfileFormValue,
  toProfilePayload,
} from "@/components/profile/profile-form";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { api, ApiError } from "@/lib/api";
import type { Profile } from "@/lib/types";

export function AddProfileDialog({ onCreated }: { onCreated?: (p: Profile) => void }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState<ProfileFormValue>({ ...emptyProfile, relationship: "parent" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const qc = useQueryClient();
  const create = useMutation({
    mutationFn: () => api.post<Profile>("/profiles", toProfilePayload(value)),
    onSuccess: (p) => {
      toast.success(`${p.display_name}'s profile created`);
      qc.invalidateQueries({ queryKey: ["profiles"] });
      setOpen(false);
      setValue({ ...emptyProfile, relationship: "parent" });
      onCreated?.(p);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 422) setErrors(fieldErrors(e.detail));
      else toast.error(e.message);
    },
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" size="sm" />}>
        <UserPlus /> Add family member
      </DialogTrigger>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add a family member</DialogTitle>
          <DialogDescription>Manage a parent&apos;s or child&apos;s records from your account.</DialogDescription>
        </DialogHeader>
        <form
          id="add-profile"
          onSubmit={(e) => {
            e.preventDefault();
            setErrors({});
            create.mutate();
          }}
        >
          <ProfileFields value={value} onChange={setValue} errors={errors} forSomeoneElse />
        </form>
        <DialogFooter>
          <Button type="submit" form="add-profile" disabled={create.isPending}>
            {create.isPending && <Loader2 className="animate-spin" />} Create profile
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
