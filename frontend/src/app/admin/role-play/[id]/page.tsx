import RolePlaySessionPage from "@/features/role-play/components/session-page";
export default async function Page({params}:{params:Promise<{id:string}>}) {const {id}=await params;return <RolePlaySessionPage id={id} recruiter/>;}
