import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Untappd Beer History",
    short_name: "Beer History",
    description: "Your private beer history, trends, and favorite places.",
    start_url: "/dashboard",
    display: "standalone",
    background_color: "#0d1512",
    theme_color: "#d99b43",
    icons: [
      {
        src: "/favicon.ico",
        sizes: "any",
        type: "image/x-icon",
      },
    ],
  };
}
