import { redirect } from "next/navigation";

export default function CashPage() {
  redirect("/ledger?tab=cash");
}
