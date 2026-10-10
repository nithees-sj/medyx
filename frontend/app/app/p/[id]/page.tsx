import { redirect } from "next/navigation";

export default async function ProfileIndex({ params }: PageProps<"/app/p/[id]">) {
  const { id } = await params;
  redirect(`/app/p/${id}/timeline`);
}
