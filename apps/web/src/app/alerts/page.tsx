import { redirect } from "next/navigation";

export default function AlertsPage() {
  redirect("/monitor?tab=alerts");
}
