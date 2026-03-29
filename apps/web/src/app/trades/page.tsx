import { redirect } from "next/navigation";

export default function TradesPage() {
  redirect("/ledger?tab=trades");
}
