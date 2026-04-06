import { redirect } from "next/navigation";

export default function LegacyScreen2Redirect() {
  redirect("/screen-1");
}