use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

use cosmwasm_std::{Addr, Timestamp, Uint64};
use cw_storage_plus::{Item, Map};

use crate::msg::{Coin, CopyrightInfo};

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq, JsonSchema)]
pub struct Config {
    pub admin: Addr,
    pub register_fee: Option<Coin>,
    pub total_copyrights: Uint64,
}

pub const CONFIG: Item<Config> = Item::new("config");

pub const COPYRIGHTS: Map<&str, CopyrightStored> = Map::new("copyrights");

pub const BY_OWNER: Map<(&str, &str), ()> = Map::new("by_owner");

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq, JsonSchema)]
pub struct CopyrightStored {
    pub copyright_id: String,
    pub owner: Addr,
    pub original_hash: String,
    pub watermarked_hash: String,
    pub wm_bit_length: u32,
    pub metadata: Option<cosmwasm_std::Binary>,
    pub record_hash: String,
    pub registered_at: Timestamp,
    pub registered_height: Uint64,
}

impl CopyrightStored {
    pub fn into_info(self, tx_hash: Option<String>) -> CopyrightInfo {
        CopyrightInfo {
            copyright_id: self.copyright_id,
            owner: self.owner.to_string(),
            original_hash: self.original_hash,
            watermarked_hash: self.watermarked_hash,
            wm_bit_length: self.wm_bit_length,
            metadata: self.metadata,
            record_hash: self.record_hash,
            registered_at: self.registered_at,
            registered_height: self.registered_height,
            tx_hash,
        }
    }
}
