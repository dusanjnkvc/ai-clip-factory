import Factory from "@/components/factory";
import UnifiedWorkspace from '@/components/unified-workspace';
export default function Page() { return process.env.NEXT_PUBLIC_BROWSER_MODE==='true'?<Factory/>:<UnifiedWorkspace/>; }
