"use client";

import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalBody,
  Accordion,
  AccordionItem,
  Chip,
} from "@nextui-org/react";

interface Field {
  key: string;
  type: string;
  default?: string;
  description: string;
}

interface Section {
  title: string;
  yamlPath?: string;
  description?: string;
  fields: Field[];
}

const SECTIONS: Section[] = [
  {
    title: "General",
    description: "Top-level settings.",
    fields: [
      { key: "timezone", type: "string", default: "UTC", description: 'Timezone for scheduling. E.g. "Europe/Paris", "America/New_York".' },
      { key: "date_format", type: "DD/MM | MM/DD", default: "DD/MM", description: "Order of day and month in displayed dates." },
      { key: "tmdb_api_key", type: "string", description: "TMDB API key. Required for the Next Airing poster view." },
    ],
  },
  {
    title: "Plex",
    yamlPath: "plex:",
    fields: [
      { key: "url", type: "string", default: "http://localhost:32400", description: "URL of your Plex Media Server." },
      { key: "token", type: "string", description: "Plex authentication token (X-Plex-Token)." },
      { key: "libraries.anime", type: "list[string]", description: "Anime library names. Used by Anime Episode Type (episode matching), TV Status Tracker (status overlays), and Size Overlay." },
      { key: "libraries.tv", type: "list[string]", description: "TV show library names. Used by TV Status Tracker and Size Overlay." },
      { key: "libraries.movie", type: "list[string]", description: "Movie library names. Used by Size Overlay." },
    ],
  },
  {
    title: "Trakt",
    yamlPath: "trakt:",
    fields: [
      { key: "client_id", type: "string", description: "Trakt API application client ID." },
      { key: "client_secret", type: "string", description: "Trakt API application client secret." },
      { key: "username", type: "string", description: "Your Trakt username." },
      { key: "redirect_uri", type: "string", default: "urn:ietf:wg:oauth:2.0:oob", description: "OAuth redirect URI. Use the default unless you have a custom app." },
      { key: "access_token", type: "string", description: "OAuth access token — set automatically after authentication." },
      { key: "refresh_token", type: "string", description: "OAuth refresh token — set automatically after authentication." },
    ],
  },
  {
    title: "Lists",
    yamlPath: "lists:",
    fields: [
      { key: "default_privacy", type: "private | public", default: "private", description: "Default visibility for newly created Trakt lists." },
    ],
  },
  {
    title: "Kometa Config",
    yamlPath: "kometa_config:",
    fields: [
      { key: "yaml_output_dir", type: "string", default: "/kometa/config/overlays", description: "Directory where DAKOSYS writes Kometa overlay YAML files." },
      { key: "collections_dir", type: "string", default: "/kometa/config/collections", description: "Directory where DAKOSYS writes Kometa collections YAML files." },
      { key: "font_directory", type: "string", default: "config/fonts", description: "Path to the fonts directory used in overlays." },
      { key: "asset_directory", type: "string", default: "config/assets", description: "Path to the assets directory used in overlays." },
    ],
  },
  {
    title: "Scheduler",
    yamlPath: "scheduler:",
    description: "Configure when each service runs. Each service key (anime_episode_type, tv_status_tracker, size_overlay) accepts the same schedule fields.",
    fields: [
      { key: "type", type: "daily | hourly | weekly | monthly | cron | run", description: "Schedule type. \"run\" means run once at startup only." },
      { key: "times", type: "list[HH:MM]", default: '["03:00"]', description: "Used with type: daily. One or more times to run each day." },
      { key: "minute", type: "integer", default: "0", description: "Used with type: hourly. Which minute of the hour to run." },
      { key: "days", type: "list[string]", default: '["monday"]', description: 'Used with type: weekly. Day names e.g. ["monday", "friday"].' },
      { key: "time", type: "HH:MM", default: "03:00", description: "Used with type: weekly and monthly. Time of day to run." },
      { key: "dates", type: "list[integer]", default: "[1]", description: "Used with type: monthly. Day numbers of the month e.g. [1, 15]." },
      { key: "expression", type: "cron string", default: "0 3 * * *", description: 'Used with type: cron. Standard 5-part cron expression e.g. "0 3 * * *".' },
      { key: "scheduled_anime", type: "list[string]", description: "AFL slugs of anime to auto-update on each Anime Episode Type run." },
    ],
  },
  {
    title: "Service — Anime Episode Type",
    yamlPath: "services:\n  anime_episode_type:",
    description: "Manages Trakt lists of anime episodes categorised by type (filler, manga canon, anime canon, mixed). Requires Trakt VIP.",
    fields: [
      { key: "enabled", type: "boolean", default: "false", description: "Enable or disable this service." },
      { key: "libraries", type: "list[string]", description: "Plex library names this service operates on." },
      { key: "overlay.horizontal_align", type: "left | center | right", default: "center", description: "Horizontal anchor of the overlay banner." },
      { key: "overlay.horizontal_offset", type: "integer", default: "0", description: "Pixel offset from the horizontal anchor." },
      { key: "overlay.vertical_align", type: "top | center | bottom", default: "top", description: "Vertical anchor of the overlay banner." },
      { key: "overlay.vertical_offset", type: "integer", default: "0", description: "Pixel offset from the vertical anchor." },
      { key: "overlay.font_size", type: "integer", default: "75", description: "Font size in pixels." },
      { key: "overlay.back_width", type: "integer", default: "1920", description: "Banner background width in pixels." },
      { key: "overlay.back_height", type: "integer", default: "125", description: "Banner background height in pixels." },
      { key: "overlay.back_color", type: "hex color", default: "#262626", description: "Banner background color." },
    ],
  },
  {
    title: "Service — TV Status Tracker",
    yamlPath: "services:\n  tv_status_tracker:",
    description: "Creates Kometa overlays showing a show's airing status (AIRING, ENDED, RETURNING, etc.) and upcoming air dates.",
    fields: [
      { key: "enabled", type: "boolean", default: "false", description: "Enable or disable this service." },
      { key: "libraries", type: "list[string]", description: "Plex library names this service operates on." },
      { key: "colors.AIRING", type: "hex color", default: "#006580", description: "Overlay background color for currently airing shows." },
      { key: "colors.ENDED", type: "hex color", default: "#000000", description: "Overlay background color for ended shows." },
      { key: "colors.CANCELLED", type: "hex color", default: "#FF0000", description: "Overlay background color for cancelled shows." },
      { key: "colors.RETURNING", type: "hex color", default: "#008000", description: "Overlay background color for returning shows." },
      { key: "colors.SEASON_FINALE", type: "hex color", default: "#9932CC", description: "Overlay background color for season finales." },
      { key: "colors.MID_SEASON_FINALE", type: "hex color", default: "#FFA500", description: "Overlay background color for mid-season finales." },
      { key: "colors.FINAL_EPISODE", type: "hex color", default: "#8B0000", description: "Overlay background color for the final episode." },
      { key: "colors.SEASON_PREMIERE", type: "hex color", default: "#228B22", description: "Overlay background color for season premieres." },
      { key: "labels.ended", type: "string", default: "E N D E D", description: "Display text for ended shows. Overrides the English default." },
      { key: "labels.cancelled", type: "string", default: "C A N C E L L E D", description: "Display text for cancelled shows." },
      { key: "labels.returning", type: "string", default: "R E T U R N I N G", description: "Display text for returning shows." },
      { key: "labels.airing", type: "string", default: "AIRING", description: "Display text for airing shows. Air date is appended automatically." },
      { key: "labels.season_finale", type: "string", default: "SEASON FINALE", description: "Display text for season finales. Air date is appended." },
      { key: "labels.mid_season_finale", type: "string", default: "MID SEASON FINALE", description: "Display text for mid-season finales. Air date is appended." },
      { key: "labels.final_episode", type: "string", default: "FINAL EPISODE", description: "Display text for final episodes. Air date is appended." },
      { key: "labels.season_premiere", type: "string", default: "SEASON PREMIERE", description: "Display text for season premieres. Air date is appended." },
      { key: "overlay.overlay_style", type: "background_color | gradient", default: "background_color", description: "Whether to use a solid background color or a gradient image." },
      { key: "overlay.apply_gradient_background", type: "boolean", default: "false", description: "Apply a gradient image behind the status text." },
      { key: "overlay.gradient_name", type: "string", default: "gradient_top.png", description: "Gradient image filename (must exist in asset_directory)." },
      { key: "overlay.font_name", type: "string", default: "Juventus-Fans-Bold.ttf", description: "Font filename (must exist in font_directory)." },
      { key: "overlay.font_size", type: "integer", default: "70", description: "Font size in pixels." },
      { key: "overlay.color", type: "hex color", default: "#FFFFFF", description: "Text color." },
      { key: "overlay.back_width", type: "integer", default: "1000", description: "Banner background width in pixels." },
      { key: "overlay.back_height", type: "integer", default: "90", description: "Banner background height in pixels." },
      { key: "overlay.horizontal_align", type: "left | center | right", default: "center", description: "Horizontal anchor." },
      { key: "overlay.horizontal_offset", type: "integer", default: "0", description: "Pixel offset from horizontal anchor." },
      { key: "overlay.vertical_align", type: "top | center | bottom", default: "top", description: "Vertical anchor." },
      { key: "overlay.vertical_offset", type: "integer", default: "0", description: "Pixel offset from vertical anchor." },
    ],
  },
  {
    title: "Service — Size Overlay",
    yamlPath: "services:\n  size_overlay:",
    description: "Creates Kometa overlays showing file sizes and episode counts for movies and TV shows.",
    fields: [
      { key: "enabled", type: "boolean", default: "false", description: "Enable or disable this service." },
      { key: "movie_libraries", type: "list[string]", description: "Plex movie library names." },
      { key: "tv_libraries", type: "list[string]", description: "Plex TV show library names." },
      { key: "anime_libraries", type: "list[string]", description: "Plex anime library names." },
      { key: "movie_overlay.font_path", type: "string", description: "Relative path to font file for movie overlays." },
      { key: "movie_overlay.font_size", type: "integer", default: "63", description: "Font size for movie overlays." },
      { key: "movie_overlay.font_color", type: "hex color", default: "#FFFFFF", description: "Text color for movie overlays." },
      { key: "movie_overlay.back_color", type: "hex color", default: "#000000", description: "Background color for movie overlays." },
      { key: "movie_overlay.back_width", type: "integer", default: "1920", description: "Banner width for movie overlays." },
      { key: "movie_overlay.back_height", type: "integer", default: "125", description: "Banner height for movie overlays." },
      { key: "movie_overlay.horizontal_align", type: "left | center | right", default: "center", description: "Horizontal anchor for movie overlay." },
      { key: "movie_overlay.horizontal_offset", type: "integer", default: "0", description: "Pixel offset from horizontal anchor." },
      { key: "movie_overlay.vertical_align", type: "top | center | bottom", default: "top", description: "Vertical anchor for movie overlay." },
      { key: "movie_overlay.vertical_offset", type: "integer", default: "0", description: "Pixel offset from vertical anchor." },
      { key: "movie_overlay.apply_gradient_background", type: "boolean", default: "false", description: "Apply a gradient image behind the size text." },
      { key: "movie_overlay.gradient_name", type: "string", default: "gradient_top.png", description: "Gradient image filename." },
      { key: "show_overlay.font_path", type: "string", description: "Relative path to font file for show overlays." },
      { key: "show_overlay.font_size", type: "integer", default: "55", description: "Font size for show overlays." },
      { key: "show_overlay.font_color", type: "hex color", default: "#FFFFFF", description: "Text color for show overlays." },
      { key: "show_overlay.back_color", type: "hex color", default: "#00000099", description: "Background color for show overlays (supports alpha)." },
      { key: "show_overlay.back_width", type: "integer", default: "1920", description: "Banner width for show overlays." },
      { key: "show_overlay.back_height", type: "integer", default: "80", description: "Banner height for show overlays." },
      { key: "show_overlay.horizontal_align", type: "left | center | right", default: "center", description: "Horizontal anchor for show overlay." },
      { key: "show_overlay.horizontal_offset", type: "integer", default: "0", description: "Pixel offset from horizontal anchor." },
      { key: "show_overlay.vertical_align", type: "top | center | bottom", default: "bottom", description: "Vertical anchor for show overlay." },
      { key: "show_overlay.vertical_offset", type: "integer", default: "0", description: "Pixel offset from vertical anchor." },
      { key: "show_overlay.show_episode_count", type: "boolean", default: "false", description: "Append episode count to the size label (e.g. 142 GB · 24 eps)." },
      { key: "show_overlay.apply_gradient_background", type: "boolean", default: "false", description: "Apply a gradient image behind the size text." },
      { key: "show_overlay.gradient_name", type: "string", default: "gradient_bottom.png", description: "Gradient image filename." },
    ],
  },
  {
    title: "Notifications",
    yamlPath: "notifications:",
    description: "Send Discord notifications for errors, updates, and size changes.",
    fields: [
      { key: "enabled", type: "boolean", default: "false", description: "Enable or disable notifications." },
      { key: "discord.webhook_url", type: "string", description: "Discord incoming webhook URL to post notifications to." },
    ],
  },
  {
    title: "Web UI",
    yamlPath: "web_ui:",
    description: "Settings for the built-in web dashboard.",
    fields: [
      { key: "enabled", type: "boolean", default: "true", description: "Set to false to disable the web dashboard entirely." },
      { key: "port", type: "integer", default: "8000", description: "Internal port the web server listens on (map it in docker-compose.yml)." },
    ],
  },
];

function FieldRow({ field }: { field: Field }) {
  return (
    <div className="py-2 border-b border-zinc-800 last:border-0">
      <div className="flex flex-wrap items-start gap-2 mb-1">
        <code className="text-violet-300 text-xs bg-zinc-900 px-1.5 py-0.5 rounded font-mono">
          {field.key}
        </code>
        <Chip size="sm" variant="flat" className="text-xs h-5 bg-zinc-800 text-zinc-400">
          {field.type}
        </Chip>
        {field.default !== undefined && (
          <Chip size="sm" variant="flat" className="text-xs h-5 bg-zinc-900 text-zinc-500">
            default: {field.default}
          </Chip>
        )}
      </div>
      <p className="text-zinc-400 text-xs leading-relaxed">{field.description}</p>
    </div>
  );
}

interface ConfigReferenceModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ConfigReferenceModal({ isOpen, onClose }: ConfigReferenceModalProps) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      className="dark"
      size="3xl"
      scrollBehavior="inside"
    >
      <ModalContent>
        <ModalHeader className="text-white flex flex-col gap-0.5">
          <span>Config Reference</span>
          <span className="text-zinc-500 text-xs font-normal">
            All available <code className="text-violet-300">config.yaml</code> options
          </span>
        </ModalHeader>
        <ModalBody className="pb-6">
          <Accordion
            variant="splitted"
            className="gap-2 px-0"
            itemClasses={{
              base: "bg-zinc-900 border border-zinc-800 rounded-lg",
              title: "text-white text-sm font-medium",
              content: "pb-2",
              trigger: "py-3 px-4",
            }}
          >
            {SECTIONS.map((section) => (
              <AccordionItem
                key={section.title}
                title={section.title}
                subtitle={
                  section.yamlPath ? (
                    <code className="text-violet-400 text-xs font-mono">{section.yamlPath}</code>
                  ) : undefined
                }
              >
                {section.description && (
                  <p className="text-zinc-400 text-xs mb-3 px-1">{section.description}</p>
                )}
                <div className="px-1">
                  {section.fields.map((f) => (
                    <FieldRow key={f.key} field={f} />
                  ))}
                </div>
              </AccordionItem>
            ))}
          </Accordion>
        </ModalBody>
      </ModalContent>
    </Modal>
  );
}
