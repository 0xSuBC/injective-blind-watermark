use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

use cosmwasm_std::{Binary, Timestamp, Uint64};

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq, JsonSchema)]
pub struct InstantiateMsg {
    pub admin: String,
    pub register_fee: Option<Coin>,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq, JsonSchema)]
pub struct Coin {
    pub denom: String,
    pub amount: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ExecuteMsg {
    RegisterCopyright {
        copyright_id: String,
        owner: String,
        original_hash: String,
        watermarked_hash: String,
        wm_bit_length: u32,
        metadata: Option<Binary>,
        record_hash: String,
    },
    TransferCopyright {
        copyright_id: String,
        new_owner: String,
    },
    UpdateMetadata {
        copyright_id: String,
        metadata: Option<Binary>,
    },
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum QueryMsg {
    GetCopyright {
        copyright_id: String,
    },
    ListByOwner {
        owner: String,
        limit: Option<u32>,
        start_after: Option<String>,
    },
    Config {},
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq, JsonSchema)]
pub struct CopyrightInfo {
    pub copyright_id: String,
    pub owner: String,
    pub original_hash: String,
    pub watermarked_hash: String,
    pub wm_bit_length: u32,
    pub metadata: Option<Binary>,
    pub record_hash: String,
    pub registered_at: Timestamp,
    pub registered_height: Uint64,
    pub tx_hash: Option<String>,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq, JsonSchema)]
pub struct ConfigResponse {
    pub admin: String,
    pub register_fee: Option<Coin>,
    pub total_copyrights: Uint64,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq, JsonSchema)]
pub struct ListByOwnerResponse {
    pub owner: String,
    pub copyrights: Vec<CopyrightInfo>,
}
