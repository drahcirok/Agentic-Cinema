export type UserProfile = {
  uid: string;
  username: string;
  display_name: string;
  photo_url?: string | null;
  has_custom_avatar: boolean;
  created_at: string;
  updated_at: string;
};
