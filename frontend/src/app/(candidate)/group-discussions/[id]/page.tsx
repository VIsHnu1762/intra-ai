import { DiscussionSessionPage } from "@/features/group-discussion/components/session-page";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <DiscussionSessionPage id={id} />; }
