package com.ex.model;

/** Réglage modifiable à chaud, mappé par orm.xml. */
public class Setting {
    private String name;
    private String value;

    public String getValue() {
        return value;
    }
}
