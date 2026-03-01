// Legacy dashboard — redirects to /portfolio
import { redirect } from "next/navigation";

export default function DashboardPage() {
  redirect("/portfolio");
}
